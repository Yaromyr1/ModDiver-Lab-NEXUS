// SPDX-License-Identifier: GPL-3.0-only
using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
namespace HDRemix.LunaCosmetics {
    internal static class PaddingTests {
        static readonly List<string> passed=new List<string>();
        static void Check(bool yes,string message){if(!yes)throw new Exception(message);}
        static void Test(string name,Action a){a();passed.Add(name);Console.WriteLine("PASS "+name);}
        static void Refuses(Action a,string text){try{a();}catch(Exception e){Check(e.Message.IndexOf(text,StringComparison.OrdinalIgnoreCase)>=0,"Unexpected failure: "+e);return;}throw new Exception("Expected refusal: "+text);}
        static string At(string root,string rel){return Path.Combine(root,rel.Replace('/',Path.DirectorySeparatorChar));}
        internal static string[] Run(string dir,Catalog c){
            byte[] stock=File.ReadAllBytes(Path.Combine(dir,"stock-armor.bin")),plain=GameBox.Decrypt(stock),passive=File.ReadAllBytes(Path.Combine(dir,"passives.bin"));
            var blocks=SemanticEditor.ArmorBlocks(plain);var rows=blocks.ToDictionary(b=>SemanticEditor.U32(plain,b.payload));byte[] enabled=null;string stage=Path.Combine(dir,"dummy_game"),direct=Path.Combine(dir,"game-copy");var core=new ExportCore(c);Action<int,string> progress=delegate{};
            Action<string> reset=root=>{File.WriteAllBytes(At(root,ExportCore.RelativeTarget),stock);File.WriteAllBytes(At(root,ExportCore.EntityTarget),File.ReadAllBytes(Path.Combine(dir,"stock-entity.bin")));File.WriteAllBytes(At(root,ExportCore.StratagemTarget),File.ReadAllBytes(Path.Combine(dir,"stratagem.bin")));File.WriteAllBytes(At(root,ExportCore.PassiveTarget),passive);};
            Test("B-01 padding defaults off and exactly five body variants are managed",delegate{Check((Program.Options.Parse(new string[0]).mask&1024)==0,"Padding defaults on");Check(SemanticEditor.B01Variants.Length==5&&SemanticEditor.B01Variants.Distinct().Count()==5,"Wrong target set");foreach(uint id in SemanticEditor.B01Variants)Check(SemanticEditor.U32(plain,rows[id].payload+40)==0,"A helmet/cape was included");});
            Test("B-01 padding changes only five passive references plus hash footer",delegate{enabled=SemanticEditor.Armor(stock,1024,c);var after=GameBox.Decrypt(enabled);var allowed=new HashSet<int>();foreach(uint id in SemanticEditor.B01Variants){Check(SemanticEditor.U32(after,rows[id].payload+28)==1,"No Extra Padding");for(int i=0;i<4;i++)allowed.Add(rows[id].payload+28+i);}for(int i=0;i<4;i++)allowed.Add(blocks.Last().header+12+i);for(int i=0;i<plain.Length;i++)Check(plain[i]==after[i]||allowed.Contains(i),"Unrelated B-01 edit at "+i);Check(SemanticEditor.Murmur(plain)==SemanticEditor.Murmur(after),"Padding content hash");File.WriteAllBytes(Path.Combine(dir,"padding-on.bin"),enabled);});
            Test("B-01 padding disables cleanly and repeat enable keeps exact ciphertext",delegate{Check(SemanticEditor.Armor(enabled,1024,c).SequenceEqual(enabled),"Repeat padding changed ciphertext");var off=GameBox.Decrypt(SemanticEditor.Armor(enabled,0,c));foreach(uint id in SemanticEditor.B01Variants)Check(SemanticEditor.U32(off,rows[id].payload+28)==0,"Off did not restore original passive");});
            Test("custom B-01 passives are refused when selected and preserved when off",delegate{var b=(byte[])plain.Clone();int at=rows[SemanticEditor.B01Variants[0]].payload+28;Buffer.BlockCopy(BitConverter.GetBytes(9U),0,b,at,4);var input=GameBox.Encrypt(b);Refuses(()=>SemanticEditor.Armor(input,1024,c),"replace that passive");Check(SemanticEditor.Armor(input,0,c).SequenceEqual(input),"Unselected custom passive erased");});
            Test("shared customized Extra Padding is validated and never rewritten",delegate{ExportCore.ValidatePadding(passive);reset(stage);string hash=ExportCore.FileHash(At(stage,ExportCore.PassiveTarget));core.Export(stage,1215,progress,true);Check(core.DetectMask(stage)==1087,"Padding not detected on reopening");Check(ExportCore.FileHash(At(stage,ExportCore.PassiveTarget))==hash,"Shared passive file changed");});
            Test("missing or corrupt Extra Padding data stops before editing armor",delegate{reset(stage);File.WriteAllBytes(At(stage,ExportCore.PassiveTarget),new byte[]{0});string hash=ExportCore.FileHash(At(stage,ExportCore.RelativeTarget));Refuses(()=>core.Export(stage,1215,progress),"size");Check(ExportCore.FileHash(At(stage,ExportCore.RelativeTarget))==hash,"Failed padding validation wrote armor");File.Delete(At(stage,ExportCore.PassiveTarget));Refuses(()=>core.Export(stage,1215,progress),"missing");});
            Test("standalone padding backs up armor while preserving shared passive data",delegate{reset(direct);string hash=ExportCore.FileHash(At(direct,ExportCore.PassiveTarget));var d=new StandaloneCore(c,core,Path.Combine(dir,"padding-store"),()=>false,Path.Combine(dir,"empty-legacy"));d.Install(direct,1215,progress);Check(ExportCore.FileHash(At(direct,ExportCore.PassiveTarget))==hash,"Direct install changed shared passive");d.Restore(direct,progress);Check(File.ReadAllBytes(At(direct,ExportCore.RelativeTarget)).SequenceEqual(stock),"Padding exact restore failed");Check(ExportCore.FileHash(At(direct,ExportCore.PassiveTarget))==hash,"Restore changed shared passive");});
            return passed.ToArray();
        }
    }
}
