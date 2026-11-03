import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import core
import hdremix
from native_editor import Document
from portable_hash import correct_reserved, content_hash, finish_armor
from dlbin_codec import content_hash as reference_hash, DLBin


class NativeToolsTests(unittest.TestCase):
    def armor(self):
        edit = hdremix.SCHEMA['changes'][0]
        data = bytearray(4+24+64)
        struct.pack_into('<I',data,0,1)
        data[4:12]=b'LDLD\x01\0\0\0'
        struct.pack_into('<IIQ',data,12,hdremix.KIT,64,1)
        struct.pack_into('<II',data,28,edit['definition'],edit['before_tag'])
        return bytes(data),edit

    def test_hash_matches_existing_reference(self):
        for length in (0,1,7,8,9,256,259):
            data=bytes((i*37+9)%256 for i in range(length))
            self.assertEqual(content_hash(data),reference_hash(data))

    def test_reserved_solver_preserves_payload_and_length(self):
        for positions in ((8,40),(0,36)):
            original=bytearray(90)
            for pos in positions:original[pos+16]=1
            edited=bytearray(original);edited[85]=77
            headers=[(pos,1,8) for pos in positions]
            result=correct_reserved(original,edited,headers)
            self.assertIsNotNone(result)
            self.assertEqual(len(result),len(original))
            self.assertEqual(content_hash(result),content_hash(original))
            allowed={i for pos in positions for i in range(pos+17,pos+24)}
            self.assertTrue(all(a==b or i in allowed for i,(a,b) in enumerate(zip(edited,result))))

    def test_armor_padding_solver_preserves_semantic_bytes(self):
        original,_=self.armor();edited=bytearray(original);edited[32]^=1
        result=finish_armor(original,edited,hdremix.armor_headers(original))
        self.assertEqual(result[28:92],edited[28:92])
        self.assertEqual(content_hash(original),content_hash(result))
        hdremix.armor_headers(result)

    def test_unlock_profile_and_overlap_rejection(self):
        original,edit=self.armor()
        group=next(g for g in hdremix.CATALOG['groups'] if any(i['definition']==edit['definition'] for i in g['items']))
        result=core.unseal(hdremix.patch_armor(core.seal(original),group['bit']))
        self.assertEqual(struct.unpack_from('<I',result,32)[0],edit['after_tag'])
        modified=bytearray(original);struct.pack_into('<I',modified,32,123456789)
        with self.assertRaisesRegex(ValueError,'Conflicting availability'):
            hdremix.patch_armor(core.seal(bytes(modified)),group['bit'])

    def test_native_editor_roundtrip_without_lua(self):
        original,_=self.armor()
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            path=Path(folder)/hdremix.ARMOR;path.write_bytes(core.seal(original))
            document=Document(path)
            field=next(f for f in document.fields if f.label=='Passive ID')
            document.edit(field,'77')
            with patch('subprocess.run',side_effect=AssertionError('Native editor must not require Lua/exe')):
                sealed=document.prepare()
            plain=core.unseal(sealed)
            self.assertEqual(struct.unpack_from('<I',plain,28+28)[0],77)
            self.assertEqual(content_hash(plain),content_hash(original))

    def test_deploy_preserves_other_mod_fields_with_length_change(self):
        original,edit=self.armor()
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            root=Path(folder);game=root/'game';game_data=game/'data/game';game_data.mkdir(parents=True)
            original_sealed=core.seal(original);(game_data/hdremix.ARMOR).write_bytes(original_sealed)
            stock=root/'stock';stock.mkdir();(stock/hdremix.ARMOR).write_bytes(original_sealed)
            mod=root/'mod';mod.mkdir()
            changed=bytearray(original);struct.pack_into('<I',changed,56,77)
            changed=finish_armor(original,changed,hdremix.armor_headers(original))
            (mod/hdremix.ARMOR).write_bytes(core.seal(changed))
            cfg={'game':str(game),'nomofomo':True,'unlock_groups':63,'mods':[{'path':str(mod),'name':'User armor','enabled':True,'selected':{}}]}
            with patch.multiple(core,APP_DATA=root,STOCK=stock,BACKUPS=root/'backup',DEPLOYED=root/'deployed.json'),patch.dict(hdremix.CATALOG,{'build_hashes':{}}):
                core.deploy(cfg,log=lambda s:None)
                result=core.unseal((game_data/hdremix.ARMOR).read_bytes())
                self.assertEqual(struct.unpack_from('<I',result,56)[0],77)
                self.assertEqual(struct.unpack_from('<I',result,32)[0],edit['after_tag'])
                core.purge(cfg,log=lambda s:None)
                self.assertEqual((game_data/hdremix.ARMOR).read_bytes(),original_sealed)


if __name__=='__main__':unittest.main()
