// SPDX-License-Identifier: GPL-3.0-only
// Resource format/hash adaptation: SHODAN Stat Editor, commit
// 32ddd3231754927f39504a3de301885317d59542, offline/gamedata.lua.
// This edits authenticated offline assets in this utility's process only.
using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Web.Script.Serialization;

namespace HDRemix.LunaCosmetics {
    internal static class GameBox {
        const string RuntimeHash="5cfdc4bf7628777d4fd807a6f9e15ed8fb6fdaee5be65c816b3c6c3dd1c93ed1";
        // Public game-format constants from the attributed upstream source.
        static readonly byte[] PublicKey=Hex("2dc9aa7c30e6eed5f7fd0e0e95c7287299b126f79520cc41de750982ee7ff50c");
        static readonly byte[] FormatKey=Hex("a0296b81310b58f013d8a9b343a1c292008003dfd9ab15fcf351543048b49b64");
        [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)]static extern IntPtr LoadLibraryEx(string file,IntPtr reserved,uint flags);
        [DllImport("kernel32.dll",CharSet=CharSet.Ansi,ExactSpelling=true)]static extern IntPtr GetProcAddress(IntPtr module,string name);
        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate int Init();
        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate int Seal([Out]byte[] output,byte[] input,ulong length,byte[] pk);
        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]delegate int Open([Out]byte[] output,byte[] input,ulong length,byte[] pk,byte[] sk);
        static IntPtr library;static Seal seal;static Open open;static readonly object Gate=new object();
        static byte[] Hex(string s){return Enumerable.Range(0,s.Length/2).Select(i=>Convert.ToByte(s.Substring(i*2,2),16)).ToArray();}
        static T Function<T>(string name){var ptr=GetProcAddress(library,name);if(ptr==IntPtr.Zero)throw new InvalidDataException("The cryptography runtime is incomplete.");return (T)(object)Marshal.GetDelegateForFunctionPointer(ptr,typeof(T));}
        static void Ready(){lock(Gate){if(open!=null)return;
            string path=Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"Extras","Runtime","libsodium.dll");
            if(!File.Exists(path)||ExportCore.FileHash(path)!=RuntimeHash)throw new InvalidDataException("The verified cryptography runtime is missing or changed. Extract the complete release ZIP, including Extras. Do not move the EXE by itself.");
            // Full path and restricted dependency search; no PATH/current-folder DLL loading.
            library=LoadLibraryEx(path,IntPtr.Zero,0x100|0x1000);
            if(library==IntPtr.Zero)throw new IOException("Windows could not load the bundled x64 cryptography runtime (error "+Marshal.GetLastWin32Error()+"). Keep Extras beside the EXE. Error 126 can mean the Microsoft Visual C++ x64 runtime is missing; see Extras/README.md for Microsoft's official download.");
            if(Function<Init>("sodium_init")()<0)throw new IOException("Cryptography initialization failed.");
            seal=Function<Seal>("crypto_box_seal");open=Function<Open>("crypto_box_seal_open");
        }}
        internal static byte[] Decrypt(byte[] cipher){Ready();if(cipher.Length<48||cipher.Length>128*1024*1024)throw new InvalidDataException("Resource size is unsupported.");var plain=new byte[cipher.Length-48];if(open(plain,cipher,(ulong)cipher.Length,PublicKey,FormatKey)!=0)throw new InvalidDataException("Resource authentication failed. The file is damaged or uses an unsupported format; no files were changed.");return plain;}
        internal static byte[] Encrypt(byte[] plain){Ready();var result=new byte[checked(plain.Length+48)];if(seal(result,plain,(ulong)plain.Length,PublicKey)!=0)throw new IOException("Resource encryption failed.");if(!Decrypt(result).SequenceEqual(plain))throw new IOException("Encrypted resource round-trip verification failed.");return result;}
    }
    public sealed class TargetEdit { public string name;public uint definition,before_tag,after_tag; }
    public sealed class EditSchema { public Dictionary<string,int> types;public TargetEdit[] changes; }
    internal static class SemanticEditor {
        static readonly EditSchema Schema=new JavaScriptSerializer().Deserialize<EditSchema>(Encoding.UTF8.GetString(Program.Resource("Schema")));
        const ulong Mult=0xc6a4a7935bd1e995UL,Inverse=0x5f7a0ea7e59b19bdUL,Seed=0xdeadbeefabad1deaUL;
        const uint Kit=0xd9a55aa0,InteractData=0xfcca29db,Callback=0x63b171e5;
        const ulong ArcadeEntity=0x927f0eb8d641607dUL;
        internal const int PaddingBit=1024;
        internal static readonly uint[] B01Variants={0x250fd6c1,0x1d0e3431,0x708451e9,0xd59566d5,0x1369b95b};
        internal sealed class Block {internal int header,payload,size;internal uint type;}
        static void Require(bool yes,string detail){if(!yes)throw new InvalidDataException("Unsupported resource structure: "+detail+". No files were changed.");}
        internal static uint U32(byte[] b,int o){return BitConverter.ToUInt32(b,o);}
        internal static ulong U64(byte[] b,int o){return BitConverter.ToUInt64(b,o);}
        static void Put32(byte[] b,int o,uint v){Buffer.BlockCopy(BitConverter.GetBytes(v),0,b,o,4);}
        static ulong Unshift(ulong v){return v^(v>>47);}
        static ulong Mix(ulong v){unchecked{v*=Mult;v=Unshift(v);return v*Mult;}}
        static ulong Unmix(ulong v){unchecked{return Unshift(v*Inverse)*Inverse;}}
        internal static ulong Murmur(byte[] b){unchecked{
            ulong h=Seed^((ulong)b.Length*Mult);int end=b.Length&~7;
            for(int i=0;i<end;i+=8)h=(h^Mix(U64(b,i)))*Mult;
            if(end!=b.Length){ulong tail=0;for(int i=end;i<b.Length;i++)tail|=(ulong)b[i]<<((i-end)*8);h=(h^tail)*Mult;}
            return Unshift(Unshift(h)*Mult);
        }}
        internal static byte[] Finish(byte[] original,byte[] changed,Block last){
            Require(last.payload+last.size==original.Length,"final instance length");
            if(original.SequenceEqual(changed))return null;
            int correction=checked((changed.Length+7)&~7);var result=new byte[checked(correction+8)];Buffer.BlockCopy(changed,0,result,0,changed.Length);
            Put32(result,last.header+12,checked((uint)(last.size+result.Length-original.Length)));
            unchecked{ulong h=Seed^((ulong)result.Length*Mult);for(int i=0;i<correction;i+=8)h=(h^Mix(U64(result,i)))*Mult;
                ulong wanted=Unshift(Unshift(Murmur(original))*Inverse);ulong word=Unmix(h^(wanted*Inverse));Buffer.BlockCopy(BitConverter.GetBytes(word),0,result,correction,8);}
            Require(Murmur(result)==Murmur(original),"resource hash preservation");return result;
        }
        internal static Block Header(byte[] b,int h,uint type){
            Require(h>=0&&h<=b.Length-24,"instance header bounds");
            Require(U32(b,h)==0x444c444c&&U32(b,h+4)==1&&U32(b,h+8)==type&&b[h+16]==1,"LDLD version, type and pointer width");
            uint size=U32(b,h+12);Require(size<=Int32.MaxValue&&size<=b.Length-h-24,"instance payload bounds");
            return new Block{header=h,payload=h+24,size=(int)size,type=type};
        }
        internal static List<Block> ArmorBlocks(byte[] b){
            Require(b.Length>=4,"armor header");uint count=U32(b,0);Require(count>0&&count<=4096,"armor record count");var blocks=new List<Block>();var ids=new HashSet<uint>();int pos=4;
            for(int i=0;i<count;i++){var block=Header(b,pos,Kit);Require(block.size>=64,"armor kit size");Require(ids.Add(U32(b,block.payload)),"duplicate armor definition");
                int body=Array(b,block,block.payload+48,24,8);int n=(int)U32(b,block.payload+56);
                for(int j=0;j<n;j++){int pieces=Array(b,block,body+j*24+8,112,64);int m=(int)U32(b,body+j*24+16);for(int k=0;k<m;k++)Array(b,block,pieces+k*112+96,16,64);}
                blocks.Add(block);pos=checked(block.payload+block.size);}
            Require(pos==b.Length,"armor trailing instance boundary");return blocks;
        }
        static int Array(byte[] b,Block block,int descriptor,int stride,int maximum){
            Require(descriptor>=block.payload&&descriptor<=block.payload+block.size-16,"array descriptor");ulong relative=U64(b,descriptor);uint count=U32(b,descriptor+8);
            Require(count<=maximum&&U32(b,descriptor+12)==0,"array count or reserved value");if(count==0){Require(relative==0||relative==UInt64.MaxValue||relative<=(ulong)block.size,"empty array pointer");return block.payload;}
            Require(relative>=64&&relative<=(ulong)block.size&&(ulong)count*(ulong)stride<=(ulong)block.size-relative,"array bounds");return checked(block.payload+(int)relative);
        }
        internal static List<Block> EntityBlocks(byte[] b){
            var found=new List<Block>();int next=0;
            for(int h=4;h<=b.Length-24;h++){if(h<next||U32(b,h)!=0x444c444c||U32(b,h+4)!=1)continue;
                uint type=U32(b,h+8);int minimum;if(!Schema.types.TryGetValue(type.ToString(System.Globalization.CultureInfo.InvariantCulture),out minimum)||U32(b,h-4)!=type)continue;
                uint size=U32(b,h+12);if(b[h+16]!=1||size<minimum||size>b.Length-h-24)continue;
                var block=Header(b,h,type);found.Add(block);next=checked(block.payload+block.size);Require(found.Count<=2048,"entity component count");}
            Require(found.Count>0&&found.Last().payload+found.Last().size==b.Length,"entity instance boundaries");return found;
        }
        internal static int ArcadeZone(byte[] b,List<Block> blocks){
            var matches=blocks.Where(x=>x.type==InteractData).ToArray();Require(matches.Length==1,"unique interactable component table");var block=matches[0];Require(block.size>=638432,"interactable table layout");
            int found=-1;
            for(int i=0;i<1124;i++){int slot=block.payload+i*16;ulong entity=U64(b,slot);if(entity==0)continue;uint value=U32(b,slot+8);Require(value<562,"interactable value index");
                if(entity==ArcadeEntity){Require(found<0,"duplicate arcade entity");found=block.payload+17984+checked((int)value*1104)+8;}}
            Require(found>=0,"Stratagem Hero entity not present");return found;
        }
        static bool KnownArcade(byte[] b,int z){return b[z+45]<=1&&(U32(b,z+48)==0xbf800000||U32(b,z+48)==0x3f800000)&&(U32(b,z+80)==0||U32(b,z+80)==Callback);}
        internal static byte[] Armor(byte[] cipher,int mask,Catalog catalog){
            byte[] original=GameBox.Decrypt(cipher),changed=(byte[])original.Clone();var blocks=ArmorBlocks(original);var byID=blocks.ToDictionary(x=>U32(original,x.payload));var edits=Schema.changes.ToDictionary(x=>x.definition);int present=0,missing=0,modified=0,preserved=0;
            foreach(var group in catalog.groups)foreach(var item in group.items){TargetEdit edit;Require(edits.TryGetValue((uint)item.definition,out edit),"target catalog/schema disagreement");Block block;bool selected=(group.bit&mask)!=0;
                if(!byID.TryGetValue(edit.definition,out block)){if(selected){missing++;Program.Log("Missing selected cosmetic definition: "+edit.name+" ("+edit.definition+"). No record was added.");}continue;}if(selected)present++;
                uint current=U32(original,block.payload+4);if(current!=edit.before_tag&&current!=edit.after_tag){if(selected)throw new InvalidDataException("Another mod changes the availability field for "+edit.name+" (definition "+edit.definition+", value 0x"+current.ToString("x8")+"). Uncheck that category or remove the overlapping edit. No files were changed.");preserved++;continue;}
                uint desired=selected?edit.after_tag:edit.before_tag;if(current!=desired){Put32(changed,block.payload+4,desired);modified++;}}
            if((mask&63)!=0&&present==0)throw new InvalidDataException("None of the selected cosmetic definitions exist in this resource. No files were changed.");
            bool padding=(mask&PaddingBit)!=0;int paddingChanged=0;
            foreach(uint id in B01Variants){Block block;if(!byID.TryGetValue(id,out block)){if(padding)throw new InvalidDataException("A colored B-01 armor definition is missing: "+id+". No files were changed.");continue;}
                Require(U32(original,block.payload+40)==0,"B-01 body armor category");uint current=U32(original,block.payload+28);
                if(current!=0&&current!=1){if(padding)throw new InvalidDataException("Another mod assigns passive "+current+" to colored B-01 armor "+id+". Extra Padding would replace that passive. Use Armor Workbench to combine effects, or leave this option off. No files were changed.");continue;}
                uint wanted=padding?1U:0U;if(current!=wanted){Put32(changed,block.payload+28,wanted);paddingChanged++;}}
            Program.Log("Colored B-01 Extra Padding: enabled="+padding+", body variants changed="+paddingChanged+"; native passive 1 is reused and its shared effects are not modified.");
            Program.Log("Semantic cosmetics: selected definitions present="+present+", missing="+missing+", changed="+modified+", unselected overlapping fields preserved="+preserved+". This is not an in-game visibility check.");
            var result=Finish(original,changed,blocks.Last());return result==null?cipher:GameBox.Encrypt(result);
        }
        internal static byte[] Arcade(byte[] cipher,bool enabled){
            byte[] original=GameBox.Decrypt(cipher),changed=(byte[])original.Clone();var blocks=EntityBlocks(original);int zone=ArcadeZone(original,blocks);
            if(!KnownArcade(original,zone))throw new InvalidDataException("Another mod changes Stratagem Hero's interaction callback, start flag or delay. This installer will preserve it. Select Leave current ship file unchanged, or remove that overlapping edit. No files were changed.");
            changed[zone+45]=(byte)(enabled?1:0);Put32(changed,zone+48,enabled?0x3f800000U:0xbf800000U);Put32(changed,zone+80,enabled?Callback:0);
            var result=Finish(original,changed,blocks.Last());Program.Log("Semantic Stratagem Hero: "+(enabled?"enabled":"disabled")+", changed="+(result!=null)+"; all other entity fields preserved.");return result==null?cipher:GameBox.Encrypt(result);
        }
        internal static int Detect(string root,Catalog catalog){
            int mask=0;string armor=Path.Combine(root,ExportCore.RelativeTarget.Replace('/',Path.DirectorySeparatorChar));
            try{var b=GameBox.Decrypt(File.ReadAllBytes(armor));var blocks=ArmorBlocks(b).ToDictionary(x=>U32(b,x.payload));var edits=Schema.changes.ToDictionary(x=>x.definition);
                foreach(var g in catalog.groups)if(g.items.Any(i=>blocks.ContainsKey((uint)i.definition)&&U32(b,blocks[(uint)i.definition].payload+4)==edits[(uint)i.definition].after_tag))mask|=g.bit;
                if(B01Variants.All(id=>blocks.ContainsKey(id)&&U32(b,blocks[id].payload+28)==1))mask|=PaddingBit;
            }catch{mask=63;}
            try{var b=GameBox.Decrypt(File.ReadAllBytes(Path.Combine(root,ExportCore.EntityTarget.Replace('/',Path.DirectorySeparatorChar))));int z=ArcadeZone(b,EntityBlocks(b));if(!KnownArcade(b,z))mask|=128;else if(b[z+45]==1&&U32(b,z+48)==0x3f800000&&U32(b,z+80)==Callback)mask|=64;else if(b[z+45]!=0||U32(b,z+48)!=0xbf800000||U32(b,z+80)!=0)mask|=128;}catch{mask|=128;}
            return mask;
        }
    }
}
