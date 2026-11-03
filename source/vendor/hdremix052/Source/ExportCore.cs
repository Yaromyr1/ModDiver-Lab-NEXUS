using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Web.Script.Serialization;

namespace HDRemix.LunaCosmetics {
    public sealed class Item { public long definition; public string name; public string category; }
    public sealed class Group { public int bit; public string id; public string name; public string description; public Item[] items; }
    public sealed class Catalog {
        public string version,stock_armor_original; public int game_build; public Group[] groups;
        public string[] legacy_stock_inputs; public Dictionary<string,string> build_hashes;
        internal static Catalog Parse(byte[] bytes) {
            var c=new JavaScriptSerializer().Deserialize<Catalog>(Encoding.UTF8.GetString(bytes));
            if(c==null || c.game_build!=26251122 || c.groups==null || c.groups.Length!=6 || c.groups.Any(g=>g==null||g.items==null) ||
                c.groups.Sum(g=>g.items.Length)!=111 || c.groups.SelectMany(g=>g.items).Select(i=>i.definition).Distinct().Count()!=111 ||
                !c.groups.Select(g=>g.bit).SequenceEqual(new[]{1,2,4,8,16,32}) || c.build_hashes==null || c.build_hashes.Count!=3 ||
                c.stock_armor_original==null || c.stock_armor_original.Length!=64 || c.legacy_stock_inputs==null)
                throw new InvalidDataException("The category catalog is damaged. Download a fresh copy.");
            return c;
        }
    }
    internal sealed class ExportCore {
        internal const string RelativeTarget="data/game/generated_customization_armor_sets.dl_bin";
        internal const string EntityTarget="data/game/generated_entities.dl_bin";
        internal const string StratagemTarget="data/game/generated_stratagem_settings.dl_bin";
        internal const string PassiveTarget="data/game/generated_customization_passive_bonuses.dl_bin";
        readonly Catalog catalog;
        internal Action AfterReplaceForTest;
        internal Action<int> AfterCommitForTest;
        sealed class Change { internal string target,before,temp,rollback; internal string after; internal int bytes; internal byte[] payload; internal bool changed; }
        sealed class Plan { internal string root,armorHash; internal Dictionary<string,string> snapshot=new Dictionary<string,string>(); internal List<Change> changes=new List<Change>(); }
        internal ExportCore(Catalog data) { catalog=data; }
        internal static string Hash(byte[] bytes) {
            using(var s=SHA256.Create())return BitConverter.ToString(s.ComputeHash(bytes)).Replace("-","").ToLowerInvariant();
        }
        internal static string FileHash(string path) {
            using(var f=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.Read))
            using(var s=SHA256.Create())return BitConverter.ToString(s.ComputeHash(f)).Replace("-","").ToLowerInvariant();
        }
        static void ValidateMask(int mask) { if(mask<0 || (mask&~1279)!=0 || (mask&192)==192)throw new InvalidDataException("The category selection is invalid."); }
        internal int DetectMask(string path) {return SemanticEditor.Detect(NormalizeStage(path),catalog);}
        internal static string NormalizeStage(string path) {
            if(String.IsNullOrWhiteSpace(path))throw new InvalidDataException("Paste the staging folder shown by Luna first.");
            string root=Path.GetFullPath(path.Trim().Trim('"')).TrimEnd(Path.DirectorySeparatorChar,Path.AltDirectorySeparatorChar);
            if(!String.Equals(Path.GetFileName(root),"dummy_game",StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("Use Luna's dummy_game staging folder, not the real Helldivers 2 folder. Copy the folder from Luna's Configure prompt.");
            if(!Directory.Exists(root))throw new DirectoryNotFoundException("The staging folder does not exist. Start Configure in Luna first.");
            for(var d=new DirectoryInfo(root);d!=null;d=d.Parent)
                if((d.Attributes&FileAttributes.ReparsePoint)!=0)throw new InvalidDataException("The staging path contains a directory link. Use Luna's normal staging folder.");
            return root;
        }
        static string Child(string root,string relative) {
            string full=Path.GetFullPath(Path.Combine(root,relative.Replace('/',Path.DirectorySeparatorChar)));
            if(!full.StartsWith(root+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new InvalidDataException("Output path escapes staging.");
            for(var d=new FileInfo(full).Directory;d!=null && d.FullName.Length>=root.Length;d=d.Parent)
                if(d.Exists && (d.Attributes&FileAttributes.ReparsePoint)!=0)throw new InvalidDataException("A staging subfolder is a directory link. Export stopped.");
            if(File.Exists(full) && (File.GetAttributes(full)&FileAttributes.ReparsePoint)!=0)throw new InvalidDataException("A staging input is a file link. Export stopped.");
            return full;
        }
        static string Watch(Plan plan,string path) {
            string hash=File.Exists(path)?FileHash(path):null;plan.snapshot.Add(path,hash);return hash;
        }
        Plan Prepare(string path,int mask,bool captureForLoader=false) {
            ValidateMask(mask);var plan=new Plan {root=NormalizeStage(path)};
            foreach(var witness in catalog.build_hashes) {
                string p=Child(plan.root,witness.Key);
                if(Watch(plan,p)!=witness.Value)throw new InvalidDataException("The staging copy does not match supported game build 26251122. Refresh Luna's dummy after updating the game. No files were exported.");
            }
            if((mask&SemanticEditor.PaddingBit)!=0){string passive=Child(plan.root,PassiveTarget);string passiveHash=Watch(plan,passive);
                if(passiveHash==null)throw new InvalidDataException("Extra Padding's passive table is missing. Refresh Luna's dummy before enabling colored B-01 Extra Padding.");
                ValidatePadding(File.ReadAllBytes(passive));if(FileHash(passive)!=passiveHash)throw new IOException("The passive table changed while it was being checked.");}
            string armor=Child(plan.root,RelativeTarget);plan.armorHash=Watch(plan,armor);
            if(plan.armorHash==null && (mask&63)!=0)throw new InvalidDataException("Luna's staged armor catalog is missing. Refresh the dummy and configure again.");
            if(plan.armorHash!=null) {
                byte[] input=File.ReadAllBytes(armor),output=SemanticEditor.Armor(input,mask,catalog);
                if(Hash(input)!=plan.armorHash)throw new IOException("The staged armor changed while being read.");
                if(captureForLoader && input.SequenceEqual(output)) {
                    // Luna captures changed ciphertext, even when its baseline already has
                    // these settings. Re-seal the identical authenticated plaintext without
                    // adding another footer or making a gameplay-data change.
                    output=GameBox.Encrypt(GameBox.Decrypt(input));
                    Program.Log("Luna capture: cosmetic settings already present; resealed identical plaintext for explicit configuration capture.");
                }
                Add(plan,armor,plan.armorHash,output);
            }
            PrepareLegacySwapCleanup(plan);
            if((mask&128)!=0)return plan;
            string entity=Child(plan.root,EntityTarget),entityHash=Watch(plan,entity);
            if(entityHash==null)throw new InvalidDataException("The staged entity resource is missing. Refresh Luna's dummy, or select Leave current ship file unchanged.");
            byte[] entityInput=File.ReadAllBytes(entity),entityOutput=SemanticEditor.Arcade(entityInput,(mask&64)!=0);
            if(Hash(entityInput)!=entityHash)throw new IOException("The staged entity changed while being read.");
            if(captureForLoader && entityInput.SequenceEqual(entityOutput)) {
                entityOutput=GameBox.Encrypt(GameBox.Decrypt(entityInput));
                Program.Log("Luna capture: Stratagem Hero setting already present; resealed identical plaintext for explicit configuration capture.");
            }
            Add(plan,entity,entityHash,entityOutput);
            return plan;
        }
        internal static void ValidatePadding(byte[] cipher){
            byte[] b=GameBox.Decrypt(cipher);if(b.Length<4)throw new InvalidDataException("The passive table is truncated.");uint count=SemanticEditor.U32(b,0);if(count==0||count>512)throw new InvalidDataException("Unsupported passive table count.");int at=4;bool found=false;
            for(int i=0;i<count;i++){var block=SemanticEditor.Header(b,at,0x63ce0feb);if(block.size<56)throw new InvalidDataException("Unsupported passive record size.");
                if(SemanticEditor.U32(b,block.payload)==1){if(found||SemanticEditor.U32(b,block.payload+4)!=4207037112U)throw new InvalidDataException("Native passive 1 is not an unambiguous Extra Padding entry.");found=true;
                    ulong p=SemanticEditor.U64(b,block.payload+16),n=SemanticEditor.U64(b,block.payload+24);if(n==0||n>256||p<56||p>(ulong)block.size||n*16>(ulong)block.size-p)throw new InvalidDataException("Extra Padding's modifier array is unsupported.");
                    bool armor=false;for(int j=0;j<(int)n;j++){int pos=block.payload+(int)p+j*16;float value=BitConverter.ToSingle(b,pos+8);if(SemanticEditor.U32(b,pos)==2947431239U&&SemanticEditor.U32(b,pos+4)==1&&value>0&&!Single.IsInfinity(value)&&!Single.IsNaN(value))armor=true;}
                    if(!armor)throw new InvalidDataException("The existing Extra Padding passive has no positive native armor modifier. Its effects were not changed.");}
                at=block.payload+block.size;}
            if(at!=b.Length||!found)throw new InvalidDataException("Extra Padding was not found in the supported passive table.");
        }
        void PrepareLegacySwapCleanup(Plan plan){
            string target=Child(plan.root,StratagemTarget);
            if(!File.Exists(target))return;
            string before=Watch(plan,target);byte[] input=File.ReadAllBytes(target),output=StratagemSwaps.Restore(input);
            if(Hash(input)!=before)throw new IOException("The staged stratagem resource changed while being read.");
            Add(plan,target,before,output);
        }
        static void Add(Plan plan,string path,string before,byte[] output){string after=Hash(output);if(after!=before)plan.changes.Add(new Change{target=path,before=before,payload=output,after=after,bytes=output.Length});}
        internal string Check(string path,int mask) {return Prepare(path,mask).armorHash;}
        static void Unchanged(Plan plan) {
            foreach(var pair in plan.snapshot) {
                string now=File.Exists(pair.Key)?FileHash(pair.Key):null;
                if(now!=pair.Value)throw new IOException("A staging input changed during export. Retry after other configurators finish.");
            }
        }
        internal string Export(string path,int mask,Action<int,string> progress,bool captureForLoader=false) {
            using(var mutex=new Mutex(false,"Local\\HDRemix.NoMoFOMOCosmetics.FileTransaction")) {
                bool held=false;
                try {
                    try {held=mutex.WaitOne(0);}catch(AbandonedMutexException){held=true;}
                    if(!held)throw new IOException("Another resource operation is running. Wait for it to finish.");
                    progress(10,"Checking the staged build and selected resources...");var plan=Prepare(path,mask,captureForLoader);
                    // Validate both payloads before any staged file is replaced.
                    foreach(var change in plan.changes) {
                        if(change.payload.Length!=change.bytes || Hash(change.payload)!=change.after)
                            throw new InvalidDataException("A selected payload is damaged. Download a fresh copy.");
                    }
                    if(plan.changes.Count==0) {progress(100,"Selected settings are already staged.");return plan.armorHash;}
                    string token=Guid.NewGuid().ToString("N");
                    try {
                        foreach(var change in plan.changes) {
                            change.temp=change.target+".hdremix-"+token+".tmp";change.rollback=change.target+".hdremix-"+token+".rollback";
                            using(var f=new FileStream(change.temp,FileMode.CreateNew,FileAccess.Write,FileShare.None)) {f.Write(change.payload,0,change.payload.Length);f.Flush(true);}
                            if(FileHash(change.temp)!=change.after)throw new IOException("Staging output verification failed.");
                        }
                        Unchanged(plan);int committed=0;
                        foreach(var change in plan.changes) {
                            progress(45+committed*20,"Saving selected settings to Luna staging...");
                            if(FileHash(change.target)!=change.before)throw new IOException("A staging input changed during export.");
                            File.Replace(change.temp,change.target,change.rollback,true);change.changed=true;
                            if(FileHash(change.rollback)!=change.before || FileHash(change.target)!=change.after)throw new IOException("Export verification failed.");
                            committed++;
                            if(AfterReplaceForTest!=null)AfterReplaceForTest();
                            if(AfterCommitForTest!=null)AfterCommitForTest(committed);
                        }
                        foreach(var change in plan.changes)File.Delete(change.rollback);
                    } catch {
                        foreach(var change in plan.changes.AsEnumerable().Reverse()) {
                            if(!change.changed || !File.Exists(change.rollback))continue;
                            if(FileHash(change.rollback)!=change.before || FileHash(change.target)!=change.after)
                                throw new IOException("Staging changed during rollback. Keep diagnostic files, do not deploy, and refresh the dummy.");
                            File.Replace(change.rollback,change.target,null,true);
                            if(FileHash(change.target)!=change.before)throw new IOException("Staging rollback could not be verified. Refresh the dummy before deploying.");
                        }
                        throw;
                    } finally {foreach(var change in plan.changes)if(change.temp!=null && File.Exists(change.temp))File.Delete(change.temp);}
                    progress(100,"Export verified. Return to Luna and Deploy.");string armor=Child(plan.root,RelativeTarget);return File.Exists(armor)?FileHash(armor):null;
                } finally {if(held)mutex.ReleaseMutex();}
            }
        }
    }
}
