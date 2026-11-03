using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Collections.Generic;
using System.Threading;
using System.Web.Script.Serialization;

namespace HDRemix.LunaCosmetics {
    public sealed class OwnedFile { public string relative;public string original;public string current; }
    public sealed class InstallState { public int version=1;public string root;public OwnedFile[] files=new OwnedFile[0]; }
    public sealed class PendingFile { public string relative;public string before;public string after; }
    public sealed class PendingInstall { public InstallState before;public InstallState after;public PendingFile[] files; }
    public sealed class LegacyBackupRecord { public int Version;public string GameRoot;public string OriginalHash; }
    internal sealed class StandaloneCore {
        readonly Catalog catalog;readonly ExportCore exporter;readonly string storage,legacyStorage;readonly Func<bool> running;
        internal Action<int> AfterCommitForTest;
        internal Action BeforeLiveWriteForTest;
        internal static readonly string[] Targets={ExportCore.RelativeTarget,ExportCore.EntityTarget,ExportCore.StratagemTarget};
        internal StandaloneCore(Catalog c,ExportCore e,string s,Func<bool> gameRunning,string legacyBase=null){catalog=c;exporter=e;storage=Path.GetFullPath(s);running=gameRunning;legacyStorage=Path.GetFullPath(legacyBase??Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),"HDRemix","Unreleased Cosmetics"));}
        internal static string Root(string path){
            if(String.IsNullOrWhiteSpace(path))throw new InvalidDataException("Choose the Helldivers 2 folder containing bin and data.");
            string root=Path.GetFullPath(path.Trim().Trim('"')).TrimEnd(Path.DirectorySeparatorChar,Path.AltDirectorySeparatorChar);
            if(String.Equals(Path.GetFileName(root),"dummy_game",StringComparison.OrdinalIgnoreCase))throw new InvalidDataException("This is Luna staging. Open this helper through Luna Configure instead of direct installation.");
            if(!Directory.Exists(root))throw new DirectoryNotFoundException("The game folder does not exist.");
            NoLinks(root);return root;
        }
        static void NoLinks(string p){
            if(File.Exists(p) && (File.GetAttributes(p)&FileAttributes.ReparsePoint)!=0)throw new InvalidDataException("A selected file is a link. No files were changed.");
            for(var d=Directory.Exists(p)?new DirectoryInfo(p):new FileInfo(p).Directory;d!=null;d=d.Parent)
                if(d.Exists && (d.Attributes&FileAttributes.ReparsePoint)!=0)throw new InvalidDataException("The selected path contains a directory link. No files were changed.");
        }
        static string Child(string root,string rel){
            string p=Path.GetFullPath(Path.Combine(root,rel.Replace('/',Path.DirectorySeparatorChar)));
            if(!p.StartsWith(root+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new InvalidDataException("A resource path escapes its folder.");
            NoLinks(p);return p;
        }
        static string HashOrNull(string p){NoLinks(p);return File.Exists(p)?ExportCore.FileHash(p):null;}
        static bool IsHash(string s){return s!=null && s.Length==64 && s.All(c=>(c>='0'&&c<='9')||(c>='a'&&c<='f'));}
        void Closed(){if(running())throw new InvalidOperationException("Close Helldivers 2 completely before installing, restoring or repairing.");}
        internal string BackupFolder(string root){root=Root(root);return Child(storage,"Backups/Build-26251122/"+ExportCore.Hash(Encoding.UTF8.GetBytes(root.ToLowerInvariant())).Substring(0,32));}
        string StatePath(string root){return Child(BackupFolder(root),"install-state.json");}
        string PendingPath(string root){return Child(BackupFolder(root),"pending-transaction.json");}
        string Backup(string root,string hash){if(!IsHash(hash))throw new InvalidDataException("A backup hash is damaged.");return Child(BackupFolder(root),hash+".original");}
        static void Need(string path,string hash){if(!IsHash(hash)||HashOrNull(path)!=hash)throw new InvalidDataException("A required file is missing or changed: "+path+"\nExpected SHA-256: "+hash+"\nActual SHA-256: "+HashOrNull(path));}
        static T Read<T>(string p){
            NoLinks(p);if(!File.Exists(p)||new FileInfo(p).Length>1024*1024)throw new InvalidDataException("A backup record is missing or damaged. Keep the backup folder.");
            try{return new JavaScriptSerializer().Deserialize<T>(File.ReadAllText(p));}catch{throw new InvalidDataException("A backup record is damaged. Keep the backup folder.");}
        }
        static void WriteNew(string p,byte[] data){using(var f=new FileStream(p,FileMode.CreateNew,FileAccess.Write,FileShare.None)){f.Write(data,0,data.Length);f.Flush(true);}}
        static void Save(string p,object value){
            NoLinks(p);Directory.CreateDirectory(Path.GetDirectoryName(p));string temp=p+"."+Guid.NewGuid().ToString("N")+".tmp";
            try{WriteNew(temp,Encoding.UTF8.GetBytes(new JavaScriptSerializer().Serialize(value)));if(File.Exists(p))File.Replace(temp,p,null);else File.Move(temp,p);}
            finally{if(File.Exists(temp))File.Delete(temp);}
        }
        static void Validate(InstallState s,string root){
            if(s==null||s.version!=1||!String.Equals(s.root,root,StringComparison.OrdinalIgnoreCase)||s.files==null||s.files.Length>3||s.files.Any(f=>f==null||!Targets.Contains(f.relative)||!IsHash(f.original)||!IsHash(f.current))||s.files.Select(f=>f.relative).Distinct().Count()!=s.files.Length)
                throw new InvalidDataException("The backup record does not match this game folder. Keep all backups.");
        }
        InstallState State(string root){
            string p=StatePath(root);if(!File.Exists(p))return new InstallState{root=root};
            var s=Read<InstallState>(p);Validate(s,root);foreach(var f in s.files)Need(Backup(root,f.original),f.original);return s;
        }
        sealed class LegacyOriginal { internal string path,original,current; }
        LegacyOriginal EarlierOriginal(string root){
            // Accept an old backup only for this exact game path/build and a
            // current stock-family cosmetic output. Never erase Workbench edits.
            string current=HashOrNull(Child(root,ExportCore.RelativeTarget));
            string stockOriginal=catalog.stock_armor_original;
            if(current==stockOriginal||!catalog.legacy_stock_inputs.Contains(current))return null;
            string id=ExportCore.Hash(Encoding.UTF8.GetBytes(root.ToLowerInvariant())).Substring(0,32);
            string folder=Child(legacyStorage,"Backups/Build-26251122/"+id),record=Child(folder,"backup.json");
            if(!File.Exists(record))return null;
            try{
                var r=Read<LegacyBackupRecord>(record);
                if(r==null||r.Version!=1||!String.Equals(r.GameRoot,root,StringComparison.OrdinalIgnoreCase)||r.OriginalHash!=stockOriginal)return null;
                string original=Child(folder,r.OriginalHash+".original");Need(original,r.OriginalHash);
                return new LegacyOriginal{path=original,original=r.OriginalHash,current=current};
            }catch(InvalidDataException){return null;}
        }
        InstallState AdoptEarlierOriginal(string root,InstallState previous){
            if(previous.files.Length!=0)return previous;var legacy=EarlierOriginal(root);if(legacy==null)return previous;
            Closed();Capture(root,legacy.path,legacy.original);
            var state=new InstallState{root=root,files=new[]{new OwnedFile{relative=ExportCore.RelativeTarget,original=legacy.original,current=legacy.current}}};
            Save(StatePath(root),state);return state;
        }
        internal void VerifyBuild(string root){
            root=Root(root);foreach(var w in catalog.build_hashes){string hash=HashOrNull(Child(root,w.Key));if(hash!=w.Value)throw new InvalidDataException("Unsupported game build; 26251122 is required. Nothing was changed.\nFile: "+w.Key+"\nExpected SHA-256: "+w.Value+"\nActual SHA-256: "+(hash??"missing"));}
        }
        Dictionary<string,string> Snapshot(string root){
            return catalog.build_hashes.Keys.Concat(Targets).Concat(new[]{ExportCore.PassiveTarget}).ToDictionary(n=>n,n=>HashOrNull(Child(root,n)));
        }
        static void Same(string root,Dictionary<string,string> snapshot){foreach(var p in snapshot)if(HashOrNull(Child(root,p.Key))!=p.Value)throw new IOException("A game file changed during preparation. Nothing more will be overwritten.\nFile: "+p.Key);}
        void Capture(string root,string source,string hash){
            Need(source,hash);string backup=Backup(root,hash);Directory.CreateDirectory(Path.GetDirectoryName(backup));
            if(!File.Exists(backup)){string tmp=Path.Combine(Path.GetDirectoryName(backup),Guid.NewGuid().ToString("N")+".tmp");try{File.Copy(source,tmp);Need(tmp,hash);File.Move(tmp,backup);}finally{if(File.Exists(tmp))File.Delete(tmp);}}
            Need(backup,hash);
        }
        static void Replace(string target,string source,string expected,string wanted){
            Need(target,expected);Need(source,wanted);string token=Guid.NewGuid().ToString("N"),tmp=target+".hdremix-"+token+".tmp",rollback=target+".hdremix-"+token+".rollback";
            bool changed=false;
            try{File.Copy(source,tmp);Need(tmp,wanted);Need(target,expected);File.Replace(tmp,target,rollback,true);changed=true;Need(target,wanted);Need(rollback,expected);}
            catch{if(changed && File.Exists(rollback)){Need(target,wanted);Need(rollback,expected);File.Replace(rollback,target,null,true);Need(target,expected);}throw;}
            finally{if(File.Exists(tmp))File.Delete(tmp);if(File.Exists(rollback)&&HashOrNull(target)==wanted)File.Delete(rollback);}
        }
        void RollBack(string root,PendingInstall pending){
            Validate(pending.before,root);Validate(pending.after,root);
            if(pending.files==null||pending.files.Length<1||pending.files.Length>3||pending.files.Any(f=>!Targets.Contains(f.relative)||!IsHash(f.before)||!IsHash(f.after))||pending.files.Select(f=>f.relative).Distinct().Count()!=pending.files.Length)
                throw new InvalidDataException("The interrupted transaction record is damaged. Keep its backups.");
            // Validate every file BEFORE recovering any of them.
            foreach(var f in pending.files){string h=HashOrNull(Child(root,f.relative));if(h!=f.before && h!=f.after)throw new InvalidDataException("An interrupted-install file was changed by another mod/update. Recovery stopped.\nFile: "+f.relative+"\nSHA-256: "+h);Need(Backup(root,f.before),f.before);}
            foreach(var f in pending.files.Reverse()){Closed();string p=Child(root,f.relative),h=HashOrNull(p);if(h==f.after)Replace(p,Backup(root,f.before),f.after,f.before);}
            Save(StatePath(root),pending.before);File.Delete(PendingPath(root));
        }
        string Commit(string root,InstallState previous,InstallState next,List<PendingFile> changes,Func<PendingFile,string> payload,Dictionary<string,string> snapshot,Action<int,string> progress){
            foreach(var f in changes)Capture(root,Child(root,f.relative),f.before);
            var pending=new PendingInstall{before=previous,after=next,files=changes.ToArray()};
            if(File.Exists(PendingPath(root)))throw new InvalidDataException("An interrupted installation needs recovery. Click Restore previous files first.");
            Save(PendingPath(root),pending);bool complete=false;
            try{
                if(BeforeLiveWriteForTest!=null)BeforeLiveWriteForTest();Closed();Same(root,snapshot);
                for(int i=0;i<changes.Count;i++){var f=changes[i];Closed();progress(65+i*10,"Saving "+Path.GetFileName(f.relative)+"...");Replace(Child(root,f.relative),payload(f),f.before,f.after);if(AfterCommitForTest!=null)AfterCommitForTest(i+1);}
                Save(StatePath(root),next);complete=true;File.Delete(PendingPath(root));
            }catch{
                if(!complete){try{RollBack(root,pending);}catch(Exception e){throw new IOException("Installation stopped; automatic recovery could not finish. Keep all backups and use Restore previous files after resolving the conflict.\n"+e.Message);}}
                throw;
            }
            progress(100,"Selected files saved and verified.");return "Selected settings installed. Launch Helldivers 2 normally through Steam. Restore previous files returns to the exact files present before this installer first changed them.";
        }
        internal string Install(string path,int mask,Action<int,string> progress){
            string root=Root(path);Closed();
            using(var mutex=new Mutex(false,"Local\\HDRemix.NoMoFOMOCosmetics.FileTransaction")){
                bool held=false;string work=null;
                try{
                    try{held=mutex.WaitOne(0);}catch(AbandonedMutexException){held=true;}if(!held)throw new IOException("Another resource operation is running.");
                    VerifyBuild(root);if(File.Exists(PendingPath(root)))throw new InvalidDataException("An interrupted installation needs recovery. Click Restore previous files first.");
                    var previous=AdoptEarlierOriginal(root,State(root));var snapshot=Snapshot(root);progress(10,"Preparing an independent copy and checking selected settings...");
                    string workBase=Path.GetFullPath(Path.Combine(Path.GetTempPath(),"HDRemixInstaller"));NoLinks(workBase);
                    work=Child(workBase,Guid.NewGuid().ToString("N"));string stage=Path.Combine(work,"dummy_game");Directory.CreateDirectory(stage);
                    foreach(var p in snapshot.Where(p=>p.Value!=null)){string dest=Path.Combine(stage,p.Key.Replace('/',Path.DirectorySeparatorChar));Directory.CreateDirectory(Path.GetDirectoryName(dest));File.Copy(Child(root,p.Key),dest);Need(dest,p.Value);}
                    Same(root,snapshot);exporter.Export(stage,mask,delegate(int n,string s){progress(15+n/3,s);});
                    var changes=new List<PendingFile>();var owned=previous.files.Select(f=>new OwnedFile{relative=f.relative,original=f.original,current=f.current}).ToList();
                    foreach(string rel in Targets){string after=HashOrNull(Path.Combine(stage,rel.Replace('/',Path.DirectorySeparatorChar))),before=snapshot[rel];if(after==before)continue;
                        if(before==null||after==null)throw new InvalidDataException("A selected resource is missing. Nothing was installed.");
                        var f=owned.SingleOrDefault(x=>x.relative==rel);if(f!=null && before!=f.current && before!=f.original)throw new InvalidDataException("A previously installed file changed outside this helper. Keep backups and collect diagnostics.\nFile: "+rel+"\nSHA-256: "+before);
                        if(f==null){f=new OwnedFile{relative=rel,original=before};owned.Add(f);}f.current=after;
                        changes.Add(new PendingFile{relative=rel,before=before,after=after});
                    }
                    Closed();Same(root,snapshot);
                    if(changes.Count==0)return previous.files.Length==0?"These settings are already present. No files were changed and no earlier original could be inferred. Keep older installer backups; this helper has no previous files to restore yet.":"These settings are already present. Existing backups are retained.";
                    var next=new InstallState{root=root,files=owned.ToArray()};
                    return Commit(root,previous,next,changes,f=>Path.Combine(stage,f.relative.Replace('/',Path.DirectorySeparatorChar)),snapshot,progress);
                }finally{
                    if(work!=null && Directory.Exists(work)){try{NoLinks(work);Directory.Delete(work,true);}catch{}}
                    if(held)mutex.ReleaseMutex();
                }
            }
        }
        internal string Restore(string path,Action<int,string> progress){
            string root=Root(path);Closed();VerifyBuild(root);
            using(var mutex=new Mutex(false,"Local\\HDRemix.NoMoFOMOCosmetics.FileTransaction")){
                bool held=false;
                try{
                    try{held=mutex.WaitOne(0);}catch(AbandonedMutexException){held=true;}if(!held)throw new IOException("Another resource operation is running.");
                    if(File.Exists(PendingPath(root))){RollBack(root,Read<PendingInstall>(PendingPath(root)));return "Interrupted installation recovered. Exact files from before that operation were restored. Older backups remain available.";}
                    var previous=AdoptEarlierOriginal(root,State(root));if(previous.files.Length==0)throw new InvalidDataException("This installer has no verified previous-file backup for this folder. Keep older helper backups. Do not delete them or install again to try to recreate a missing original.");
                    var snapshot=Snapshot(root);var changes=new List<PendingFile>();
                    foreach(var f in previous.files){string h=snapshot[f.relative];if(h==f.original)continue;if(h!=f.current)throw new InvalidDataException("Restore stopped because a file changed after this helper installed it. No files were overwritten.\nFile: "+f.relative+"\nSHA-256: "+h);Need(Backup(root,f.original),f.original);changes.Add(new PendingFile{relative=f.relative,before=h,after=f.original});}
                    if(changes.Count==0)return "Previous files are already restored. Backups were retained.";
                    var next=new InstallState{root=root,files=previous.files.Select(f=>new OwnedFile{relative=f.relative,original=f.original,current=f.original}).ToArray()};
                    Commit(root,previous,next,changes,f=>Backup(root,f.after),snapshot,progress);return "Previous files restored and verified. Other files and older backups were preserved.";
                }finally{if(held)mutex.ReleaseMutex();}
            }
        }
        internal bool HasRestore(string path){try{string root=Root(path);return File.Exists(PendingPath(root))||State(root).files.Any(f=>f.current!=f.original)||EarlierOriginal(root)!=null;}catch{return false;}}
        internal int DetectMask(string path){return SemanticEditor.Detect(Root(path),catalog);}
        internal string Diagnostics(string path){
            var report=new StringBuilder("Installer 0.5.4 / build 26251122 / standalone\r\n");
            try{string root=Root(path);report.AppendLine("Game folder: "+root);foreach(var p in Snapshot(root))report.AppendLine(p.Key+" SHA-256: "+(p.Value??"missing"));report.AppendLine("Backup folder: "+BackupFolder(root));report.AppendLine("Interrupted transaction: "+File.Exists(PendingPath(root)));report.AppendLine("Restore record available: "+HasRestore(root));report.AppendLine("Verified earlier standalone original available: "+(EarlierOriginal(root)!=null));}
            catch(Exception e){report.AppendLine(e.Message);}return report.ToString();
        }
    }
}
