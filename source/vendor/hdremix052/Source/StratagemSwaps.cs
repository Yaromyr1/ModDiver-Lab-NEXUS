// SPDX-License-Identifier: GPL-3.0-only
using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Collections.Generic;
using System.Web.Script.Serialization;
namespace HDRemix.LunaCosmetics {
    public sealed class SwapField {public int offset,bytes;public string label,before,after;public bool payload;}
    public sealed class SwapSpec {public string name;public int bit;public uint source,source_type,donor,donor_type;public SwapField[] fields;}
    public sealed class SwapCatalog {public int version,default_bits;public SwapSpec[] swaps;}
    internal static class StratagemSwaps {
        internal static readonly SwapCatalog Catalog=new JavaScriptSerializer().Deserialize<SwapCatalog>(Encoding.UTF8.GetString(Program.Resource("SwapTargets")));
        internal sealed class Row {internal SemanticEditor.Block block;internal int at;internal uint type,id;}
        static void Need(bool okay,string text){if(!okay)throw new InvalidDataException("Unsupported stratagem structure: "+text+". No files were changed.");}
        internal static List<SemanticEditor.Block> Blocks(byte[] b){
            Need(b.Length>=4,"header");uint n=SemanticEditor.U32(b,0);Need(n>0&&n<=64,"table count");int at=4;var blocks=new List<SemanticEditor.Block>();
            for(int i=0;i<n;i++){var block=SemanticEditor.Header(b,at,0x30eb6399);Need(block.size>=16,"table size");blocks.Add(block);at=checked(block.payload+block.size);}
            Need(at==b.Length,"final table boundary");return blocks;
        }
        internal static Dictionary<uint,Row> Rows(byte[] b,List<SemanticEditor.Block> blocks){
            var rows=new Dictionary<uint,Row>();foreach(var block in blocks){ulong p=SemanticEditor.U64(b,block.payload),n=SemanticEditor.U64(b,block.payload+8);
                Need(n<=512&&(n==0||p>=16)&&p<=(ulong)block.size&&n*400<=(ulong)block.size-p,"400-byte row array");
                for(int i=0;i<(int)n;i++){int at=checked(block.payload+(int)p+i*400);uint id=SemanticEditor.U32(b,at+4);Need(!rows.ContainsKey(id),"duplicate definition");rows.Add(id,new Row{block=block,at=at,id=id,type=SemanticEditor.U32(b,at)});}}
            return rows;
        }
        static int Payload(byte[] b,Row row){
            ulong pointer=SemanticEditor.U64(b,row.at+152),count=SemanticEditor.U64(b,row.at+160);
            Need(count==2&&pointer>=16&&pointer<=(ulong)row.block.size&&16<=(ulong)row.block.size-pointer,"two-part spawn payload");return checked(row.block.payload+(int)pointer);
        }
        static byte[] Hex(string text){return Enumerable.Range(0,text.Length/2).Select(i=>Convert.ToByte(text.Substring(i*2,2),16)).ToArray();}
        static bool Equal(byte[] data,int at,byte[] wanted){for(int i=0;i<wanted.Length;i++)if(data[at+i]!=wanted[i])return false;return true;}
        // Compatibility cleanup only. No enable path remains in the release.
        internal static byte[] Restore(byte[] cipher){
            byte[] original=GameBox.Decrypt(cipher),changed=(byte[])original.Clone();var blocks=Blocks(original);var rows=Rows(original,blocks);
            Need(Catalog.version==1&&Catalog.default_bits==0&&Catalog.swaps.Length==2,"legacy swap catalog");
            foreach(var spec in Catalog.swaps){Row source;
                if(!rows.TryGetValue(spec.source,out source))continue;
                Need(source.type==spec.source_type,"legacy source type for "+spec.name);int payload=Payload(original,source);
                var edits=new List<KeyValuePair<int,byte[]>>();string structuralConflict=null;
                foreach(var field in spec.fields){byte[] before=Hex(field.before),after=Hex(field.after);
                    Need(before.Length==field.bytes&&after.Length==field.bytes&&field.offset>=0&&field.offset<=400-field.bytes,"legacy field bounds");
                    int at=field.payload?payload:source.at+field.offset;
                    if(Equal(original,at,after))edits.Add(new KeyValuePair<int,byte[]>(at,before));
                    else if(!Equal(original,at,before)){
                        if(field.payload||field.label=="package")structuralConflict=field.label;
                        else Program.Log("Legacy swap cleanup preserves unfamiliar "+field.label+": "+spec.name);
                    }
                }
                if(edits.Count>0&&structuralConflict!=null)throw new InvalidDataException("Cannot safely remove an older "+spec.name+" replacement: another mod changes its "+structuralConflict+". No files were changed. Remove the old replacement configuration through Luna and reconfigure from its baseline, or restore the installer backup.");
                foreach(var edit in edits)Buffer.BlockCopy(edit.Value,0,changed,edit.Key,edit.Value.Length);
                Program.Log("Removed legacy stratagem replacement: "+spec.name+", recognized fields restored="+edits.Count+"; unrelated edits preserved.");
            }
            var output=SemanticEditor.Finish(original,changed,blocks.Last());return output==null?cipher:GameBox.Encrypt(output);
        }
    }
}
