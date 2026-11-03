using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Drawing;
using System.Reflection;
using System.Diagnostics;
using System.Collections.Generic;
using System.Threading.Tasks;
using System.Windows.Forms;
using Microsoft.Win32;

[assembly:AssemblyTitle("NoMoFOMO + Hidden Content Unlocker Mod")]
[assembly:AssemblyProduct("NoMoFOMO + Hidden Content Unlocker Mod")]
[assembly:AssemblyVersion("0.5.4.0")]
[assembly:AssemblyFileVersion("0.5.4.0")]
namespace HDRemix.LunaCosmetics {
    internal static class Program {
        internal const string Title="NoMoFOMO + Hidden Content Unlocker Mod — 0.5.4";
        internal static readonly string Storage=Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"HDRemix","NoMoFOMO Hidden Content Installer");
        internal static int ExitStatus=1;
        internal static byte[] Resource(string name){using(var i=Assembly.GetExecutingAssembly().GetManifestResourceStream(name)){if(i==null)throw new InvalidDataException("The installer is incomplete. Download a fresh copy.");using(var o=new MemoryStream()){i.CopyTo(o);return o.ToArray();}}}
        internal static void Log(string s){try{Directory.CreateDirectory(Storage);File.AppendAllText(Path.Combine(Storage,"Helper.log"),DateTime.UtcNow.ToString("o")+" "+s+Environment.NewLine);}catch{}}
        internal static bool Running(){return Process.GetProcessesByName("helldivers2").Length>0||Process.GetProcessesByName("helldivers2_launcher").Length>0;}
        internal static string FindGame(){
            var roots=new List<string>();try{using(var k=Registry.CurrentUser.OpenSubKey(@"Software\Valve\Steam"))if(k!=null)roots.Add(Convert.ToString(k.GetValue("SteamPath")));}catch{}
            roots.Add(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),"Steam"));
            foreach(string steam in roots.Where(s=>!String.IsNullOrWhiteSpace(s)).Distinct().ToArray()){
                string vdf=Path.Combine(steam,"steamapps","libraryfolders.vdf");try{if(File.Exists(vdf)&&new FileInfo(vdf).Length<1024*1024)foreach(System.Text.RegularExpressions.Match m in System.Text.RegularExpressions.Regex.Matches(File.ReadAllText(vdf),"\"path\"\\s*\"([^\"]+)\""))roots.Add(m.Groups[1].Value.Replace("\\\\","\\"));}catch{}
            }
            return roots.Where(s=>!String.IsNullOrWhiteSpace(s)).Select(s=>Path.Combine(s,"steamapps","common","Helldivers 2")).FirstOrDefault(s=>File.Exists(Path.Combine(s,"bin","helldivers2.exe")));
        }
        internal sealed class Options {
            internal bool loader,export,explicitMask;internal string root,preview;internal int mask=191;
            internal static Options Parse(string[] args){
                var o=new Options();for(int i=0;i<args.Length;i++){
                    if(args[i]=="--loader-mode")o.loader=true;
                    else if(args[i]=="--game-root"&&i+1<args.Length)o.root=args[++i];
                    else if(args[i]=="--mask"&&i+1<args.Length){o.mask=Int32.Parse(args[++i]);o.explicitMask=true;}
                    else if(args[i]=="--preview"&&i+1<args.Length)o.preview=args[++i];
                    else if(args[i]=="--export")o.export=true;
                    else throw new ArgumentException("Unknown installer option: "+args[i]);
                }
                if(o.export&&(!o.loader||o.preview!=null))throw new ArgumentException("Command-line export is available only in explicit Luna mode and cannot run during preview.");
                if(o.loader&&String.IsNullOrWhiteSpace(o.root))throw new ArgumentException("Launch this edition using Luna's Configure button so Luna can supply its staging folder. Opening the EXE normally uses standalone installation.");
                if(o.mask<0||(o.mask&~1279)!=0||((o.mask&192)==192))throw new ArgumentException("The category/arcade selection is invalid.");return o;
            }
        }
        [STAThread]static int Main(string[] args){
            Application.EnableVisualStyles();Application.SetCompatibleTextRenderingDefault(false);
            try{
                var options=Options.Parse(args);var c=Catalog.Parse(Resource("Profiles"));var core=new ExportCore(c);
                var standalone=new StandaloneCore(c,core,Storage,Running);
                string root=options.root??(options.loader?null:FindGame());int mask=options.mask;
                if(!options.explicitMask && root!=null){try{mask=options.loader?core.DetectMask(root):standalone.DetectMask(root);}catch{}}
                if(options.export){core.Export(root,mask,delegate{},true);Log("Luna export completed; mask="+mask+" stage="+root);return 0;}
                using(var form=new MainForm(c,core,standalone,options.loader,root,mask,options.preview!=null)){
                    if(options.preview!=null){form.ShowInTaskbar=false;form.Opacity=0;form.Show();Application.DoEvents();using(var b=new Bitmap(form.Width,form.Height)){form.DrawToBitmap(b,new Rectangle(Point.Empty,form.Size));b.Save(Path.GetFullPath(options.preview));}return 0;}
                    Application.Run(form);return ExitStatus;
                }
            }catch(Exception e){Log(e.ToString());MessageBox.Show(e.Message,Title,MessageBoxButtons.OK,MessageBoxIcon.Error);return 1;}
        }
    }
    internal sealed class MainForm:Form {
        readonly Catalog catalog;readonly ExportCore exporter;readonly StandaloneCore standalone;readonly bool loader,preview;
        readonly TextBox path=new TextBox();readonly CheckBox[] boxes;readonly ComboBox arcade=new ThemeComboBox();
        readonly CheckBox padding=new ThemeCheckBox();readonly Panel content=new Panel(),footer=new Panel();
        readonly Button install=new Button(),restore=new Button(),browse=new Button(),diagnostics=new Button(),logs=new Button();
        readonly Label count=new Label(),status=new Label(),stage=new Label();readonly ThemeProgress progress=new ThemeProgress();bool busy;
        internal MainForm(Catalog c,ExportCore e,StandaloneCore s,bool luna,string root,int mask,bool previewOnly){
            catalog=c;exporter=e;standalone=s;loader=luna;preview=previewOnly;
            Text=Program.Title;ClientSize=new Size(810,Math.Min(900,Screen.PrimaryScreen.WorkingArea.Height-65));StartPosition=FormStartPosition.CenterScreen;FormBorderStyle=FormBorderStyle.FixedDialog;MaximizeBox=false;
            AutoScaleMode=AutoScaleMode.Dpi;AutoScaleDimensions=new SizeF(96,96);Font=new Font("Segoe UI",10);BackColor=MenuTheme.Background;ForeColor=MenuTheme.Text;
            content.Dock=DockStyle.Fill;content.AutoScroll=true;content.AutoScrollMinSize=new Size(0,660);content.BackColor=MenuTheme.Background;Controls.Add(content);
            footer.Dock=DockStyle.Bottom;footer.Height=184;footer.BackColor=MenuTheme.Background;Controls.Add(footer);content.BringToFront();
            Label("NoMoFOMO +\nHidden Content Unlocker Mod",24,15,760,72,20,true,MenuTheme.Accent);
            Label("0.5.4 / BUILD 26251122 / "+(loader?"LUNA EXPORT":"STANDALONE INSTALLER"),27,94,754,23,9,false,MenuTheme.Muted);
            Label(loader?"Configure here, then Deploy through Luna. Luna manages backups and Purge.":"Installs into your game folder and keeps verified previous-file backups.",27,123,754,26,10,false,MenuTheme.Muted);
            Label(loader?"Luna staging folder (from Luna Configure)":"Helldivers 2 game folder",27,158,754,23,10,true,MenuTheme.Accent);
            path.SetBounds(27,188,633,30);path.Text=root??"";path.BackColor=MenuTheme.Panel;path.ForeColor=MenuTheme.Text;path.BorderStyle=BorderStyle.FixedSingle;content.Controls.Add(path);
            browse.Text="Browse...";browse.SetBounds(672,184,110,34);MenuTheme.Button(browse);browse.Click+=delegate{Choose();};content.Controls.Add(browse);
            var cosmetics=new ThemeGroupBox{Text="Cosmetic categories",ForeColor=MenuTheme.Accent,BackColor=MenuTheme.Background};cosmetics.SetBounds(26,235,756,246);content.Controls.Add(cosmetics);
            boxes=new CheckBox[c.groups.Length];for(int i=0;i<boxes.Length;i++){var g=c.groups[i];var check=new ThemeCheckBox{Text=g.name+" ("+g.items.Length+")",Checked=(mask&g.bit)!=0};check.SetBounds(16,25+i*31,720,28);check.CheckedChanged+=delegate{Selection();};boxes[i]=check;cosmetics.Controls.Add(check);new ToolTip().SetToolTip(check,g.description);}
            count.SetBounds(17,215,245,24);count.ForeColor=MenuTheme.Muted;count.Font=new Font("Segoe UI",9);cosmetics.Controls.Add(count);
            padding.Text="Extra Padding for colored B-01 armor";padding.Checked=(mask&1024)!=0;padding.SetBounds(278,211,460,29);padding.CheckedChanged+=delegate{Selection();};cosmetics.Controls.Add(padding);
            var hero=new ThemeGroupBox{Text="Stratagem Hero",ForeColor=MenuTheme.Accent,BackColor=MenuTheme.Background};hero.SetBounds(26,497,756,82);content.Controls.Add(hero);
            arcade.DropDownStyle=ComboBoxStyle.DropDownList;MenuTheme.Combo(arcade);arcade.Items.AddRange(new object[]{"Leave current ship file unchanged","Enable Stratagem Hero","Disable Stratagem Hero"});arcade.SelectedIndex=(mask&128)!=0?0:((mask&64)!=0?1:2);
            arcade.SetBounds(16,29,724,32);arcade.SelectedIndexChanged+=delegate{Selection();};hero.Controls.Add(arcade);
            Label("FRV and Dark Fluid replacements removed. Recognized older swaps are restored when saving.",27,596,754,48,9,false,MenuTheme.Muted);
            status.SetBounds(27,8,754,36);status.ForeColor=MenuTheme.Accent;footer.Controls.Add(status);
            progress.SetBounds(27,48,754,6);footer.Controls.Add(progress);stage.SetBounds(27,59,754,20);stage.Font=new Font("Segoe UI",9);stage.ForeColor=MenuTheme.Muted;footer.Controls.Add(stage);
            install.Text=loader?"SAVE SETTINGS TO LUNA":"INSTALL SELECTED SETTINGS";install.SetBounds(27,83,754,44);MenuTheme.Button(install,true);install.Click+=delegate{Apply(false);};footer.Controls.Add(install);
            restore.Text="Restore previous files";restore.SetBounds(27,137,221,36);restore.Visible=!loader;MenuTheme.Button(restore);restore.Click+=delegate{Apply(true);};footer.Controls.Add(restore);
            diagnostics.Text="Diagnostics";diagnostics.SetBounds(loader?27:263,137,170,36);MenuTheme.Button(diagnostics);diagnostics.Click+=delegate{ShowDiagnostics();};footer.Controls.Add(diagnostics);
            logs.Text="Open logs folder";logs.SetBounds(610,137,171,36);MenuTheme.Button(logs);logs.Click+=delegate{try{Directory.CreateDirectory(Program.Storage);Process.Start(Program.Storage);}catch(Exception ex){status.Text=ex.Message;}};footer.Controls.Add(logs);
            path.TextChanged+=delegate{Selection();};FormClosing+=delegate(object sender,FormClosingEventArgs args){if(busy)args.Cancel=true;};Selection();ActiveControl=install;
        }
        void Label(string text,int x,int y,int w,int h,float size,bool bold,Color color){content.Controls.Add(new Label{Text=text,Location=new Point(x,y),Size=new Size(w,h),Font=new Font("Segoe UI",size,bold?FontStyle.Bold:FontStyle.Regular),ForeColor=color});}
        int Mask(){int m=0;for(int i=0;i<boxes.Length;i++)if(boxes[i]!=null&&boxes[i].Checked)m|=catalog.groups[i].bit;if(arcade.SelectedIndex==0)m|=128;else if(arcade.SelectedIndex==1)m|=64;if(padding.Checked)m|=1024;return m;}
        void Selection(){if(boxes==null)return;int mask=Mask();count.Text=catalog.groups.Where(g=>(g.bit&mask)!=0).Sum(g=>g.items.Length)+" of 111 cosmetic targets selected";
            install.Enabled=!busy;restore.Enabled=!busy&&!loader&&standalone.HasRestore(path.Text);
            if(!busy)status.Text=loader?"Choose settings, save to Luna, then Deploy through Luna.":"Close the game before installing or restoring. Earlier helper backups are preserved.";
        }
        void Choose(){using(var d=new FolderBrowserDialog{Description=loader?"Choose Luna's dummy_game folder":"Choose the Helldivers 2 folder containing bin and data",ShowNewFolderButton=false}){if(Directory.Exists(path.Text))d.SelectedPath=path.Text;if(d.ShowDialog(this)==DialogResult.OK)path.Text=d.SelectedPath;}}
        void SetBusy(bool value){busy=value;path.ReadOnly=value;browse.Enabled=!value;arcade.Enabled=!value;padding.Enabled=!value;foreach(var b in boxes)b.Enabled=!value;install.Enabled=!value;restore.Enabled=!value&&!loader&&standalone.HasRestore(path.Text);diagnostics.Enabled=!value;logs.Enabled=!value;}
        async void Apply(bool remove){
            if(busy||preview)return;SetBusy(true);progress.Value=0;string root=path.Text;int mask=Mask();
            try{
                string result=await Task.Factory.StartNew(()=>{
                    Action<int,string> p=delegate(int n,string message){BeginInvoke((Action)delegate{progress.Value=n;stage.Text=message;});};
                    if(loader){if(remove)throw new InvalidOperationException("Use Luna Purge to restore its files.");exporter.Export(root,mask,p,true);return "Settings saved to Luna staging for capture. Return to Luna and Deploy. Use Luna to disable or remove this mod.";}
                    return remove?standalone.Restore(root,p):standalone.Install(root,mask,p);
                });
                Program.Log((loader?"Luna":"Standalone")+" "+(remove?"restore":"install/export")+" mask="+mask+" folder="+root+"\n"+result);status.Text=result;Program.ExitStatus=0;
                MessageBox.Show(this,result,Program.Title,MessageBoxButtons.OK,MessageBoxIcon.Information);
                if(loader){SetBusy(false);Close();return;}
            }catch(UnauthorizedAccessException ex){Program.Log(ex.ToString());status.Text="Windows denied file access. Close the game and check folder permissions. For a protected game folder, run this installer as administrator. Do not delete backups.";MessageBox.Show(this,status.Text,Program.Title,MessageBoxButtons.OK,MessageBoxIcon.Error);}
            catch(Exception ex){Program.Log(ex.ToString());status.Text=ex.Message;MessageBox.Show(this,ex.Message+"\n\nUse Diagnostics and Open logs when reporting this problem.",Program.Title,MessageBoxButtons.OK,MessageBoxIcon.Error);}
            SetBusy(false);
        }
        void ShowDiagnostics(){
            string text;
            if(loader){var b=new StringBuilder("Installer 0.5.4 / Luna export / build 26251122\r\n");try{string root=ExportCore.NormalizeStage(path.Text);b.AppendLine("Staging folder: "+root);foreach(string rel in catalog.build_hashes.Keys.Concat(StandaloneCore.Targets)){string p=Path.Combine(root,rel.Replace('/',Path.DirectorySeparatorChar));b.AppendLine(rel+" SHA-256: "+(File.Exists(p)?ExportCore.FileHash(p):"missing"));}}catch(Exception ex){b.AppendLine(ex.Message);}text=b.ToString();}
            else text=standalone.Diagnostics(path.Text);
            text+="\r\nSelected mask: "+Mask()+"\r\nHelper log: "+Path.Combine(Program.Storage,"Helper.log")+"\r\nEarlier standalone backups: %PROGRAMDATA%\\HDRemix\\Unreleased Cosmetics\r\nInclude mod order and the exact error. This report does not observe gameplay.";
            Program.Log(text);using(var f=new Form{Text="Diagnostics —",ClientSize=new Size(740,480),StartPosition=FormStartPosition.CenterParent,BackColor=MenuTheme.Background}){var box=new TextBox{Multiline=true,ReadOnly=true,ScrollBars=ScrollBars.Both,Dock=DockStyle.Fill,WordWrap=false,Font=new Font("Consolas",9),Text=text,BackColor=MenuTheme.Panel,ForeColor=MenuTheme.Text,BorderStyle=BorderStyle.FixedSingle};var copy=new Button{Text="Copy report",Dock=DockStyle.Bottom,Height=36};MenuTheme.Button(copy);copy.Click+=delegate{try{Clipboard.SetText(text);}catch{}};f.Controls.Add(box);f.Controls.Add(copy);f.ShowDialog(this);}
        }
    }
}
