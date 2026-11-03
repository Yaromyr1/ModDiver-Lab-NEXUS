using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Text.RegularExpressions;
using System.Windows.Forms;
using System.Threading;
using System.Security.Cryptography;
using System.Text;

[assembly: AssemblyTitle("ModDiver Lab")]
[assembly: AssemblyProduct("ModDiver Lab")]
[assembly: AssemblyDescription("ModDiver Lab")]

// ModDiver Laboratory launcher (API 3).
//
// This EXE is a thin bootstrapper. The application lives in versioned folders:
//     %LOCALAPPDATA%\ModDiverLab\app\<version>\      (immutable once created)
//     %LOCALAPPDATA%\ModDiverLab\app\current.txt     line 1 = active version, line 2 = previous
// The in-app updater installs new folders and rewrites current.txt; this EXE does not change.
// The EXE embeds a "seed" copy of one app version (app.zip + app.version) and the Python runtime
// (runtime.zip). The seed is only used on first run, or when it is newer than what is installed.
//
// Keep this file C# 5 compatible (the .NET Framework csc.exe has no string interpolation, ?., etc.).
internal static class Launcher
{
    // Bump only when the contract between launcher and app changes. Packages declare
    // "min_launcher" in app.json; the updater refuses packages that need a newer launcher.
    private const int LauncherApi = 3;
    private const string OkMarker = ".app-ok";
    private const int EarlyExitWatchMs = 4000;

    private static string _exeDir;
    private static string _logPath;

    private static void Log(string text)
    {
        if (_logPath == null) return;
        try
        {
            FileInfo info = new FileInfo(_logPath);
            if (info.Exists && info.Length > 256 * 1024) info.Delete();
            File.AppendAllText(_logPath, DateTime.Now.ToString("s") + " " + text + "\n");
        }
        catch { }
    }

    // ---------------------------------------------------------------- versions

    private static bool IsSafeVersion(string v)
    {
        return v != null && Regex.IsMatch(v, @"^\d+(\.\d+)*$");
    }

    private static int[] ParseVersion(string v)
    {
        List<int> parts = new List<int>();
        if (v != null)
        {
            foreach (Match m in Regex.Matches(v.Split(new string[] { "-rollback-" }, StringSplitOptions.None)[0], @"\d+"))
            {
                int n;
                if (int.TryParse(m.Value, out n)) parts.Add(n);
            }
        }
        return parts.ToArray();
    }

    private static int CompareVersions(string a, string b)
    {
        int[] x = ParseVersion(a);
        int[] y = ParseVersion(b);
        int len = Math.Max(x.Length, y.Length);
        for (int i = 0; i < len; i++)
        {
            int xi = i < x.Length ? x[i] : 0;
            int yi = i < y.Length ? y[i] : 0;
            if (xi != yi) return xi < yi ? -1 : 1;
        }
        return 0;
    }

    // ---------------------------------------------------------------- resources / extraction

    private static string ReadResourceText(string name)
    {
        using (Stream s = Assembly.GetExecutingAssembly().GetManifestResourceStream(name))
        {
            if (s == null) return null;
            using (StreamReader r = new StreamReader(s)) { return r.ReadToEnd().Trim(); }
        }
    }

    private static void ExtractResource(string resource, string dir, string tmpDir)
    {
        string zip = Path.Combine(tmpDir, resource + "." + Guid.NewGuid().ToString("N").Substring(0, 8) + ".tmp");
        using (Stream s = Assembly.GetExecutingAssembly().GetManifestResourceStream(resource))
        {
            if (s == null) throw new InvalidOperationException("Missing embedded " + resource);
            using (FileStream f = File.Create(zip)) { s.CopyTo(f); }
        }
        try { ZipFile.ExtractToDirectory(zip, dir); }
        finally { try { File.Delete(zip); } catch { } }
    }

    // ---------------------------------------------------------------- app folders

    private static bool AppReady(string appRoot, string version)
    {
        if (!IsSafeAppFolder(version)) return false;
        string dir = Path.Combine(appRoot, version);
        bool appFiles = File.Exists(Path.Combine(dir, OkMarker)) &&
                        File.Exists(Path.Combine(dir, "yao_forge.py"));
        if (!appFiles) return false;
        // Nexus packages intentionally omit CCM and mark the app root in their seed.
        // Standard releases retain the original editor-presence check, which also
        // repairs same-version standard installs missing that bundled editor.
        if (File.Exists(Path.Combine(dir, "nexus-build.json"))) return true;
        return File.Exists(Path.Combine(dir, "vendor", "editor", "Combined Community Mods", "Combined Community Mods.exe"));
    }

    private static void ReadPointer(string appRoot, out string current, out string previous)
    {
        current = null;
        previous = null;
        try
        {
            string[] lines = File.ReadAllLines(Path.Combine(appRoot, "current.txt"));
            List<string> found = new List<string>();
            foreach (string line in lines)
            {
                string t = line.Trim();
                if (IsSafeAppFolder(t)) found.Add(t);
            }
            if (found.Count > 0) current = found[0];
            if (found.Count > 1) previous = found[1];
        }
        catch { }
    }

    private static void WritePointer(string appRoot, string current, string previous)
    {
        string target = Path.Combine(appRoot, "current.txt");
        string tmp = Path.Combine(appRoot, ".current." + Guid.NewGuid().ToString("N").Substring(0, 8) + ".tmp");
        File.WriteAllText(tmp, current + "\n" + (previous != null ? previous + "\n" : ""));
        if (File.Exists(target)) File.Replace(tmp, target, null);
        else File.Move(tmp, target);
    }

    private static bool IsSafeAppFolder(string name)
    {
        return name != null && Regex.IsMatch(name, @"\A\d+(\.\d+)*(-rollback-[0-9a-f]{8})?\z");
    }

    // Install the embedded seed when nothing usable is installed, or when the seed is newer
    // (for example a user downloaded a fresh full ZIP after skipping several updates).
    private static void InstallSeedIfNeeded(string baseDir, string appRoot, ref string current, ref string previous)
    {
        string seed = ReadResourceText("app.version");
        if (!IsSafeVersion(seed))
        {
            if (current != null && AppReady(appRoot, current)) return;
            throw new InvalidOperationException("This launcher has no usable embedded app version.");
        }

        bool currentOk = current != null && AppReady(appRoot, current);
        string revision = ReadResourceText("ui.revision").Trim();
        try
        {
            string[] pin = File.ReadAllLines(Path.Combine(appRoot, "rollback.txt"));
            if (currentOk && pin.Length == 2 && pin[0] == current && pin[1] == revision) return;
        }
        catch (IOException) { }
        string installedRevision = "";
        try { installedRevision = File.ReadAllText(Path.Combine(appRoot, seed, "ui_revision.txt")).Trim(); }
        catch (IOException) { }
        // Refresh an older build of this same public version while preserving
        // user data and leaving a newer installed release alone.
        bool refreshSeed = current != null && CompareVersions(current, seed) == 0 && revision.Length > 0 && installedRevision != revision;
        // This corrected build restores the requested 2.1.0 public version after
        // the local 2.1.1-2.1.3 builds. Preserve them as rollback targets and do
        // not replace any later release.
        bool resetVersion = seed == "2.1.0" && (revision == "2.1.0-library-presets-and-continuous-gradient"
            || revision == "2.1.0-foreground-dialogs-and-storage-checkboxes")
            && (current == "2.1.1" || current == "2.1.2" || current == "2.1.3");
        if (resetVersion && installedRevision != revision) refreshSeed = true;
        if (currentOk && CompareVersions(seed, current) <= 0 && !refreshSeed && !resetVersion) return;

        string target = Path.Combine(appRoot, seed);
        if (!AppReady(appRoot, seed) || refreshSeed)
        {
            string stage = Path.Combine(appRoot, ".staging-" + seed + "-" + Guid.NewGuid().ToString("N").Substring(0, 8));
            Directory.CreateDirectory(stage);
            try
            {
                ExtractResource("app.zip", stage, baseDir);
                File.WriteAllText(Path.Combine(stage, OkMarker), seed);
                if (Directory.Exists(target))
                {
                    string backup = seed + "-rollback-" + Guid.NewGuid().ToString("N").Substring(0, 8);
                    bool preserve = currentOk && current == seed;
                    Directory.Move(target, Path.Combine(appRoot, backup));
                    if (preserve) previous = backup;
                }
                Directory.Move(stage, target);
                Log("seed app " + seed + " installed");
            }
            catch
            {
                try { Directory.Delete(stage, true); } catch { }
                throw;
            }
        }

        string newPrevious = currentOk && current != seed ? current : previous;
        WritePointer(appRoot, seed, newPrevious);
        previous = newPrevious;
        current = seed;
    }

    // ---------------------------------------------------------------- starting the app

    private static Process StartApp(string baseDir, string legacyDir, string runtimeDir, string appRoot, string version)
    {
        string appDir = Path.Combine(appRoot, version);
        string py = Path.Combine(runtimeDir, "ModDiver Lab-" + ReadResourceText("app.version").Trim() + ".exe");
        ProcessStartInfo psi = new ProcessStartInfo(py, "\"" + Path.Combine(appDir, "yao_forge.py") + "\"");
        psi.WorkingDirectory = appDir;
        psi.UseShellExecute = false;
        psi.EnvironmentVariables["YAO_FORGE_DATA"] = baseDir;
        psi.EnvironmentVariables["YAO_FORGE_LEGACY_DATA"] = legacyDir;
        psi.EnvironmentVariables["YAO_FORGE_EXE"] = Assembly.GetExecutingAssembly().Location;
        psi.EnvironmentVariables["YAO_FORGE_LAUNCHER_API"] = LauncherApi.ToString();
        Log("starting app " + version + " from " + appDir);
        return Process.Start(psi);
    }

    // If a freshly installed version dies right away, go back to the previous one instead of
    // leaving the user with an app that will not open.
    private static Process StartWithFallback(string baseDir, string legacyDir, string runtimeDir, string appRoot,
                                          string current, string previous)
    {
        Process p = StartApp(baseDir, legacyDir, runtimeDir, appRoot, current);
        bool exited = false;
        int code = 0;
        try
        {
            exited = p.WaitForExit(EarlyExitWatchMs);
            if (exited) code = p.ExitCode;
        }
        catch { }

        if (!exited || code == 0)
        {
            Log("app " + current + " running");
            return p;
        }

        Log("app " + current + " exited early with code " + code);
        if (previous != null && AppReady(appRoot, previous))
        {
            WritePointer(appRoot, previous, null);
            // A modal warning here blocks the bootstrapper before it closes the
            // STARTING splash, leaving the warning hidden behind that splash.
            // Record the rollback and open the working version immediately.
            Log("version " + current + " failed to start (exit code " + code + "); automatically rolling back to " + previous);
            return StartApp(baseDir, legacyDir, runtimeDir, appRoot, previous);
        }
        else
        {
            MessageBox.Show("ModDiver Laboratory " + current + " failed to start (exit code " + code + ").\n\n" +
                            "Details are in " + _logPath, "ModDiver Laboratory",
                            MessageBoxButtons.OK, MessageBoxIcon.Error);
            return null;
        }
    }

    // True when another ModDiver app process is alive; its folder must not be deleted underneath it.
    private static bool OtherInstancesRunning(Process own)
    {
        try
        {
            foreach (Process other in Process.GetProcessesByName("pythonw"))
            {
                if (own == null || other.Id != own.Id) return true;
            }
            foreach (Process other in Process.GetProcessesByName("ModDiver Lab"))
            {
                if (own == null || other.Id != own.Id) return true;
            }
        }
        catch { return true; }
        return false;
    }

    // Best effort only; never delete the active or previous version, and never block startup.
    private static void Cleanup(string baseDir, string appRoot, string current, string previous)
    {
        try
        {
            foreach (string dir in Directory.GetDirectories(appRoot))
            {
                string name = Path.GetFileName(dir);
                if (name == current || name == previous) continue;
                if (name.StartsWith(".staging-") && (DateTime.UtcNow - Directory.GetLastWriteTimeUtc(dir)).TotalHours < 2) continue;
                try { Directory.Delete(dir, true); Log("removed old folder " + name); } catch { }
            }
        }
        catch { }

        // Folders and files left by launcher versions before the app/ layout.
        try
        {
            foreach (string dir in Directory.GetDirectories(baseDir, "app_*"))
            {
                try { Directory.Delete(dir, true); Log("removed legacy folder " + Path.GetFileName(dir)); } catch { }
            }
            foreach (string file in Directory.GetFiles(baseDir, "app_*.zip"))
            {
                try { File.Delete(file); } catch { }
            }
            foreach (string file in Directory.GetFiles(baseDir, "*.zip.*.tmp"))
            {
                try { File.Delete(file); } catch { }
            }
        }
        catch { }
    }

    private static string DataFolderName()
    {
#if NEXUS_BUILD
        return "ModDiverLabNexus";
#else
        return "ModDiverLab";
#endif
    }

    [STAThread]
    private static void Main()
    {
        Mutex startup = null;
        bool ownsStartup = false;
        _exeDir = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
        try
        {
            string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
            string legacyDir = Path.Combine(local, DataFolderName() == "ModDiverLabNexus" ? "YAOModForgeNexus" : "YAOModForge");
            string baseDir = Path.Combine(local, DataFolderName());
            try
            {
                Directory.CreateDirectory(baseDir);
                string probe = Path.Combine(baseDir, ".write_test");
                File.WriteAllText(probe, "1");
                File.Delete(probe);
            }
            catch
            {
                baseDir = Path.Combine(_exeDir, DataFolderName() + "Data");
                legacyDir = Path.Combine(_exeDir, DataFolderName() == "ModDiverLabNexus" ? "YAOForgeNexusData" : "YAOForgeData");
                Directory.CreateDirectory(baseDir);
            }
            // The log lives with the user's data, not next to the EXE, so it cannot end up in a release ZIP.
            _logPath = Path.Combine(baseDir, "launcher.log");
            Log("start (launcher api " + LauncherApi + ") base " + baseDir);
            string lockName;
            using (SHA256 hash = SHA256.Create())
                lockName = BitConverter.ToString(hash.ComputeHash(Encoding.UTF8.GetBytes(baseDir.ToLowerInvariant()))).Replace("-", "");
            startup = new Mutex(false, @"Local\ModDiverLab.Startup." + lockName);
            try { ownsStartup = startup.WaitOne(0); }
            catch (AbandonedMutexException) { ownsStartup = true; }
            if (!ownsStartup) return;

            string background = "#080808";
            string caption = "#141414";
            string captionText = "#ffffff";
            string secondary = "#ffd400";
            try
            {
                Match bg = Regex.Match(File.ReadAllText(Path.Combine(baseDir, "config.json")), "\"bg\"\\s*:\\s*\"(#[0-9a-fA-F]{6})\"");
                if (bg.Success) background = bg.Groups[1].Value;
                string config = File.ReadAllText(Path.Combine(baseDir, "config.json"));
                Match panel = Regex.Match(config, "\"panel\"\\s*:\\s*\"(#[0-9a-fA-F]{6})\"");
                Match text = Regex.Match(config, "\"text\"\\s*:\\s*\"(#[0-9a-fA-F]{6})\"");
                if (panel.Success) caption = panel.Groups[1].Value;
                if (text.Success) captionText = text.Groups[1].Value;
                Match accent = Regex.Match(config, "\"accent\"\\s*:\\s*\"(#[0-9a-fA-F]{6})\"");
                if (accent.Success) secondary = accent.Groups[1].Value;
            }
            catch { }
            ModDiverLoading.Show(background, caption, captionText, secondary);
            string runtimeDir = Path.Combine(baseDir, "python");
            if (!File.Exists(Path.Combine(runtimeDir, ".runtime-ok")))
            {
                if (Directory.Exists(runtimeDir)) Directory.Delete(runtimeDir, true);
                Directory.CreateDirectory(runtimeDir);
                ExtractResource("runtime.zip", runtimeDir, baseDir);
                File.WriteAllText(Path.Combine(runtimeDir, ".runtime-ok"), "1");
                Log("runtime ready");
            }
            // A new name refreshes Task Manager's icon without replacing a running interpreter.
            string brandedPython = Path.Combine(runtimeDir, "ModDiver Lab-" + ReadResourceText("app.version").Trim() + ".exe");
            if (!File.Exists(brandedPython))
            {
                using (Stream resource = Assembly.GetExecutingAssembly().GetManifestResourceStream("moddiver-python.exe"))
                using (FileStream target = File.Create(brandedPython))
                    resource.CopyTo(target);
                Log("ModDiver Lab runtime identity installed");
            }

            string appRoot = Path.Combine(baseDir, "app");
            Directory.CreateDirectory(appRoot);

            string current;
            string previous;
            ReadPointer(appRoot, out current, out previous);
            InstallSeedIfNeeded(baseDir, appRoot, ref current, ref previous);

            if (current == null || !AppReady(appRoot, current))
                throw new InvalidOperationException("No usable app version is installed.");

            Process running = StartWithFallback(baseDir, legacyDir, runtimeDir, appRoot, current, previous);

            ModDiverLoading.Close();
            if (!OtherInstancesRunning(running))
            {
                string nowCurrent;
                string nowPrevious;
                ReadPointer(appRoot, out nowCurrent, out nowPrevious);
                Cleanup(baseDir, appRoot, nowCurrent, nowPrevious);
            }
        }
        catch (Exception ex)
        {
            ModDiverLoading.Close();
            Log(ex.ToString());
            MessageBox.Show("ModDiver Laboratory could not start:\n\n" + ex.Message, "ModDiver Laboratory",
                            MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
        finally
        {
            ModDiverLoading.Close();
            if (ownsStartup) startup.ReleaseMutex();
            if (startup != null) startup.Dispose();
        }
    }
}
