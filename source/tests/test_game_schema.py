import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import core
from game_schema import Library,name_hash
from schema_document import Document


def fixture(bad_array=False,unknown_label=False):
    # A root dynamic array containing two typed records; schema and payload are
    # synthetic and independent of game files or community layout versions.
    def member(atom,storage,identity,size,offset):
        return (struct.pack('<IIIBBHI',0,0xffffffff,0,atom,storage,0,identity)+
                struct.pack('<9I',size,size,4,4,offset,offset,0xffffffff,0,0)+bytes(16))
    header=struct.pack('<9I',0x444C544C,4,2,1,4,2,0,0,0)
    enum_id=name_hash('TestEnum')
    hashes=struct.pack('<3I',1000,2000,enum_id)
    types=struct.pack('<9I',0,1,16,16,8,8,1,0,0xffffffff)
    types+=struct.pack('<9I',0,0,12,12,4,4,3,1,0xffffffff)
    enums=struct.pack('<8I',0,0,6,2,0,0,0,0xffffffff)
    members=member(1,20,2000,16,0)+member(0,16,enum_id,4,0)+member(0,2,0,4,4)+member(0,8,0,4,8)
    values=struct.pack('<IIQIIQ',0,0xffffffff,1,0,0xffffffff,2)
    data=header+hashes+types+enums+members+values
    names={1000:'RootStats',2000:'WeaponStats',enum_id:'TestEnum'}
    label='UnknownFloat' if unknown_label else 'Range'
    go={'rootstats':[(16,[(0,16,'Items','DLArray')],'RootStats')],
        'weaponstats':[(12,[(0,4,'Mode','enum.TestEnum'),(4,4,'Damage','int32'),(8,4,label,'float32')],'WeaponStats')]}
    enum_names={enum_id:{1:'Laser',2:'Cannon'}}
    payload=struct.pack('<qQ',999999 if bad_array else 16,2)+struct.pack('<IifIif',1,100,10.0,2,200,20.0)
    plain=struct.pack('<I',1)+b'LDLD\x01\0\0\0'+struct.pack('<IIQ',1000,len(payload),1)+payload
    return data,(names,go,enum_names),plain


class SchemaTests(unittest.TestCase):
    def document(self,folder,bad=False,unknown=False):
        data,refs,plain=fixture(bad,unknown)
        with patch('game_schema.references',return_value=refs):lib=Library(data)
        path=Path(folder)/'generated_test.dl_bin';path.write_bytes(core.seal(plain))
        return Document(path,lib),plain

    def test_typed_records_and_resolved_names(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            doc,_=self.document(folder)
            self.assertEqual(len(doc.entries),3)
            self.assertIn('Laser',doc.entries[1].label)
            self.assertIn('Cannon',doc.entries[2].label)
            props=doc.properties(doc.entries[1])
            self.assertEqual([(p.label,p.value) for p in props],[('Mode',1),('Damage',100),('Range',10.0)])
            self.assertEqual([p.code for p in props],['I','i','f'])

    def test_integer_edit_does_not_reinterpret_float_bits(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            doc,_=self.document(folder);props=doc.properties(doc.entries[1])
            doc.edit(props[1],'250')
            self.assertEqual(struct.unpack_from('<i',doc.data.payload(0,0),20)[0],250)
            self.assertEqual(struct.unpack_from('<f',doc.data.payload(0,0),24)[0],10.0)
            self.assertEqual(doc.data.float_edits[0],set())
            doc.edit(props[2],'12.5')
            self.assertIn(24,doc.data.float_edits[0])

    def test_unresolved_property_is_explicit_and_read_only(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            doc,_=self.document(folder,unknown=True);prop=doc.properties(doc.entries[1])[2]
            self.assertFalse(prop.editable)
            self.assertIn('unresolved',prop.note.lower())
            with self.assertRaises(ValueError):doc.edit(prop,'3.0')

    def test_enum_constraint_rejects_invalid_value(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            doc,_=self.document(folder);prop=doc.properties(doc.entries[1])[0]
            with self.assertRaises(ValueError):doc.edit(prop,'99')
            doc.edit(prop,'2')
            self.assertEqual(doc.properties(doc.entries[1])[0].value,2)

    def test_out_of_bounds_array_is_not_traversed(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            doc,_=self.document(folder,bad=True)
            self.assertEqual(len(doc.entries),1)
            self.assertTrue(doc.issues)
            self.assertFalse(any(p.editable for p in doc.properties(doc.entries[0])))

    def test_unchanged_document_preserves_ciphertext(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            doc,_=self.document(folder)
            self.assertEqual(doc.prepare(),(doc.data.sealed,[]))

    def test_truncated_library_rejected(self):
        data,refs,_=fixture()
        with patch('game_schema.references',return_value=refs):
            with self.assertRaises(ValueError):Library(data[:-1])

    def test_opt_in_footer_preserves_exact_integer_edit(self):
        from portable_hash import content_hash
        from dlbin_codec import DLBin
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            doc,plain=self.document(folder)
            prop=doc.properties(doc.entries[1])[1];doc.edit(prop,'250')
            sealed,adjustments=doc.prepare(allow_footer=True)
            result=DLBin('checked',sealed)
            self.assertEqual(struct.unpack_from('<i',result.payload(0,0),20)[0],250)
            self.assertEqual(content_hash(result.plain),content_hash(plain))
            self.assertEqual(adjustments,[])
            self.assertGreater(len(result.plain),len(plain))

    def test_inline_array_matches_contiguous_named_reference_scalars(self):
        data,refs,plain=fixture();data=bytearray(data)
        # WeaponStats now describes its final two scalars as an int32[2].
        struct.pack_into('<I',data,84+24,2)
        pos=152+72*2
        struct.pack_into('<BBH',data,pos+12,2,2,2)
        struct.pack_into('<II',data,pos+20,8,8)
        refs[1]['weaponstats'][0][1][2]=(8,4,'DurableDamage','int32')
        with patch('game_schema.references',return_value=refs):lib=Library(data)
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            path=Path(folder)/'test.dl_bin';path.write_bytes(core.seal(plain));doc=Document(path,lib)
            props=doc.properties(doc.entries[1])
            self.assertEqual([p.label for p in props],['Mode','Damage','Durable Damage'])
            self.assertTrue(all(p.editable for p in props))
            doc.edit(props[2],'55')
            self.assertEqual(struct.unpack_from('<ii',doc.payload(0),20),(100,55))

    def test_reference_mismatch_stops_subsequent_labels(self):
        data,refs,_=fixture()
        refs[1]['weaponstats'][0][1][1]=(4,4,'Damage','float32')
        with patch('game_schema.references',return_value=refs):lib=Library(data)
        self.assertTrue(lib.types[2000].members[0].trusted)
        self.assertFalse(any(m.trusted for m in lib.types[2000].members[1:]))

    def test_stripped_enum_names_keep_declared_identity_read_only(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            doc,_=self.document(folder)
            doc.library.enums={}
            record=doc.entry(0,16,2000,0)
            self.assertFalse(record.named)
            self.assertTrue(record.mapped)
            self.assertIn('Test Enum=1',record.label)
            self.assertIn('mapped identity',record.label)
            self.assertEqual(doc.data.replacements,{})

    def test_entity_sentinel_and_unknown_resource_mapping(self):
        from game_schema import Type,Member
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            doc,_=self.document(folder)
            doc.library.types[3000]=Type(3000,'EntitySettings',32,[Member(0,0,7,0,0,8,0,'Resource',trusted=True)])
            with patch.object(doc,'payload',return_value=struct.pack('<QqQII',0,-1,0,0xffffffff,0)):
                self.assertIn('empty slot',doc.entry(0,0,3000,0).label)
            with patch.object(doc,'payload',return_value=struct.pack('<QqQII',0x123456789ABCDEF0,32,1,17,0)),patch('schema_document.resource_names',return_value={}):
                entry=doc.entry(0,0,3000,0)
                self.assertTrue(entry.mapped)
                self.assertFalse(entry.named)
                self.assertIn('0x123456789ABCDEF0',entry.label)

    def test_exact_resource_match_labels_record_without_trusting_field(self):
        from game_schema import Type,Member
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            doc,_=self.document(folder)
            doc.library.types[3000]=Type(3000,'ResourceRecord',8,[Member(0,0,7,0,0,8,0)])
            key=struct.unpack_from('<Q',doc.payload(0),16)[0]
            with patch('schema_document.resource_names',return_value={key:'Known resource'}):
                entry=doc.entry(0,16,3000,0)
                self.assertTrue(entry.named)
                self.assertIn('Resource: Known resource',entry.label)
                prop=doc.properties(entry)[0]
                self.assertFalse(prop.editable)
                self.assertIn('Known resource',prop.note)

    def test_empty_and_unknown_component_index_records_are_mapped(self):
        from game_schema import Type,Member
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as folder:
            doc,_=self.document(folder)
            doc.library.types[3000]=Type(3000,'ComponentIndexData',16,[Member(0,0,7,0,0,8,0),Member(1,0,6,0,0,4,8)])
            with patch('schema_document.resource_names',return_value={}):
                entry=doc.entry(0,16,3000,0)
                self.assertTrue(entry.mapped)
                self.assertFalse(entry.named)
                self.assertIn('Resource 0x',entry.label)
                with patch.object(doc,'payload',return_value=bytes(16)):
                    empty=doc.entry(0,0,3000,5)
                    self.assertTrue(empty.mapped)
                    self.assertIn('empty slot 6',empty.label)

    def test_unknown_resource_index_still_maps_its_target(self):
        from game_schema import Type,Member
        from types import SimpleNamespace
        data,refs,_=fixture()
        with patch('game_schema.references',return_value=refs):lib=Library(data)
        lib.types={
            1:Type(1,'Root',32,[Member(0,1,20,0,2,16,0),Member(1,1,20,0,3,16,16)]),
            2:Type(2,'ComponentIndexData',16,[Member(0,0,7,0,0,8,0),Member(1,0,6,0,0,4,8)]),
            3:Type(3,'Target',4,[Member(0,0,8,0,0,4,0)])}
        payload=struct.pack('<qQqQQII f',32,1,48,1,0x123456789ABCDEF0,0,0,5.0)
        resource=SimpleNamespace(index=0,type_hash=1,sizes=[len(payload)])
        fake=SimpleNamespace(resources=[resource],payload=lambda *_:payload,replacements={})
        with patch('schema_document.DLBin.open',return_value=fake),patch('schema_document.resource_names',return_value={}):
            doc=Document('unused',lib)
        target=doc.entries[-1]
        self.assertTrue(target.mapped)
        self.assertFalse(target.named)
        self.assertIn('0x123456789ABCDEF0',target.label)
        self.assertFalse(doc.properties(target)[0].editable)

    def test_signed_enum_values_use_declared_width(self):
        data,refs,_=fixture();data=bytearray(data)
        struct.pack_into('<I',data,120+8,2)
        struct.pack_into('<Q',data,152+4*72+8,0xffffffff)
        with patch('game_schema.references',return_value=refs):lib=Library(data)
        self.assertEqual(lib.enum_values[name_hash('TestEnum')],{-1,2})

    def test_network_mapping_requires_matching_key_and_valid_slot(self):
        from types import SimpleNamespace
        from game_schema import Type,Member
        from schema_document import Entry
        doc=Document.__new__(Document)
        doc.library=SimpleNamespace(types={
            1:Type(1,'EntitySettings',32,[Member(0,0,6,0,0,4,24)]),
            2:Type(2,'EntityNetworkData',8,[Member(0,0,6,0,0,4,0),Member(1,0,6,0,0,4,4)])})
        entity=Entry(0,0,1,'Known entity',True)
        good=Entry(1,0,2,'unresolved')
        wrong_key=Entry(1,8,2,'unresolved')
        bad_slot=Entry(1,16,2,'unresolved')
        doc.entries=[entity,good,wrong_key,bad_slot]
        payloads=[bytes(24)+struct.pack('<II',123,0),struct.pack('<6I',123,0,456,0,123,0xffffffff)]
        doc.payload=lambda block:payloads[block]
        doc.map_network_entities()
        self.assertTrue(good.named and good.mapped)
        self.assertIn('Known entity',good.label)
        self.assertFalse(wrong_key.mapped)
        self.assertFalse(bad_slot.mapped)

    def test_destruction_mapping_requires_complete_bijection(self):
        from types import SimpleNamespace
        from game_schema import Type,Member
        from schema_document import Entry
        doc=Document.__new__(Document)
        doc.library=SimpleNamespace(types={1:Type(1,'DestructionSettings',168,[]),2:Type(2,'DestructionHashEntry',16,[Member(0,0,7,0,0,8,0),Member(1,0,6,0,0,4,8)])})
        targets=[Entry(0,0,1,'unresolved'),Entry(1,0,1,'unresolved')]
        doc.entries=targets+[Entry(2,0,2,'hash'),Entry(2,16,2,'hash')]
        doc.payload=lambda block:struct.pack('<4Q',123,0,456,0)
        doc.map_destruction_entities()
        self.assertFalse(any(e.mapped for e in targets))
        doc.payload=lambda block:struct.pack('<4Q',123,0,456,1)
        with patch('schema_document.resource_names',return_value={123:'Known resource'}):doc.map_destruction_entities()
        self.assertTrue(targets[0].named)
        self.assertTrue(targets[1].mapped)
        self.assertFalse(targets[1].named)


if __name__=='__main__':unittest.main()
