"""Bounds-checked, lazy schema-driven views of generated game data."""
from dataclasses import dataclass
from pathlib import Path
import math
import struct
import re
import json
from functools import lru_cache

import core
import editor_names
import hdremix
from dlbin_codec import DLBin
from game_schema import CODES, friendly, known_label
from portable_hash import finish_armor,finish_tail,correct_reserved,content_hash


@dataclass
class Entry:
    block:int
    offset:int
    type_id:int
    label:str
    named:bool=False
    mapped:bool=False


@dataclass
class Property:
    block:int
    offset:int
    code:str|None
    label:str
    value:object
    editable:bool
    enum_type:int=0
    note:str=''


@lru_cache(maxsize=1)
def weapon_names():
    metadata=Path(__file__).parent/'native_names.json'
    if metadata.is_file():
        return {int(key,16):name for key,name in json.loads(metadata.read_text(encoding='utf-8'))['resources'].items()}
    path=Path(__file__).parent/'vendor/editor/SHODAN Stat Editor/app/stat_editor.lua'
    if not path.is_file():return {}
    text=path.read_text(encoding='utf-8')
    start=text.find('local WEAPONS = {')
    text=text[start:text.find('\n}',start)+2]
    return {int(key,16):name.replace("\\'", "'") for name,key in re.findall(r"\{\s*'((?:\\.|[^'\\])*)'\s*,\s*'[^']*'\s*,\s*'([0-9A-Fa-f]{16})'",text)}


@lru_cache(maxsize=1)
def resource_names():
    result={}
    path=Path(__file__).parent/'vendor/filediver/hashes.txt'
    for line in path.read_text(encoding='utf-8').splitlines():
        line=line.strip()
        if line and not line.startswith('//'):
            result[core.resource_hash(line)]=friendly(line.rsplit('/',1)[-1])+' ['+line+']'
    result.update(weapon_names())
    return result


class Document:
    def __init__(self,path,library):
        self.data=DLBin.open(path);self.library=library;self.entries=[];self.issues=[];self._payloads={}
        self.armor={r.type_hash for r in self.data.resources}=={hdremix.KIT}
        for resource in self.data.resources:
            typ=library.types.get(resource.type_hash)
            if not typ:
                self.issues.append(f'Block {resource.index}: type not present in library')
                self.entries.append(Entry(resource.index,0,resource.type_hash,library.type_name(resource.type_hash)+' [unresolved]',False));continue
            if typ.size>resource.sizes[0]:
                self.issues.append(f'Block {resource.index}: schema size exceeds payload');continue
            entry=self.entry(resource.index,0,resource.type_hash,resource.index)
            self.entries.append(entry)
            # Expand collection roots into independently selectable records. Rich
            # records such as armor kits keep nested arrays in their property view.
            if len(typ.members)<=2 and any(m.atom in (1,2) for m in typ.members):
                keyed={}
                for member in typ.members:
                    child=library.types.get(member.type_id)
                    if child and child.name=='ComponentIndexData' and child.size==16:
                        try:
                            start,count,stride=self.array(resource.index,0,member)
                            for i in range(count):
                                key,index=struct.unpack_from('<QI',self.payload(resource.index),start+i*stride)
                                if key:
                                    keyed.setdefault(index,[]).append((key,resource_names().get(key)))
                        except ValueError:pass
                for member in typ.members:
                    child=library.types.get(member.type_id)
                    if member.atom not in (1,2) or member.storage!=20 or not child:continue
                    try:
                        start,count,stride=self.array(resource.index,0,member)
                        for i in range(count):
                            record=self.entry(resource.index,start+i*stride,member.type_id,i)
                            if child.name!='ComponentIndexData' and i in keyed:
                                links=list(dict.fromkeys(keyed[i]))
                                record.label=friendly(child.name)+' — '+', '.join(name or f'Resource 0x{key:016X}' for key,name in links)
                                record.named=any(name for key,name in links)
                                record.mapped=True
                            self.entries.append(record)
                    except ValueError as exc:self.issues.append(f'Block {resource.index}: {exc}')

        self.map_network_entities()
        self.map_destruction_entities()

    def map_destruction_entities(self):
        # SHODAN stat_editor.lua destruction-map parser numbers settings in
        # file order. Require a complete one-to-one map, not just valid bounds.
        targets=[e for e in self.entries if e.offset==0 and self.library.types.get(e.type_id) and self.library.types[e.type_id].name=='DestructionSettings']
        if not targets:return
        links={};keys=set()
        for entry in self.entries:
            typ=self.library.types.get(entry.type_id)
            if not typ or typ.name!='DestructionHashEntry':continue
            if typ.size!=16 or [(m.offset,m.size,m.atom,m.storage) for m in typ.members]!=[(0,8,0,7),(8,4,0,6)]:return
            key,index=struct.unpack_from('<QQ',self.payload(entry.block),entry.offset)
            if key==0:
                if index:return
                continue
            if index>=len(targets) or index in links or key in keys:return
            links[index]=key;keys.add(key)
        if set(links)!=set(range(len(targets))):return
        for index,key in links.items():
            entry=targets[index];name=resource_names().get(key)
            entry.label=f'Destruction Settings — {name or f"Resource 0x{key:016X}"} [settings {index}]'
            entry.named=bool(name);entry.mapped=True

    def map_network_entities(self):
        """Cross-check both network key and slot against this file's entities."""
        entities=[e for e in self.entries if self.library.types.get(e.type_id) and self.library.types[e.type_id].name=='EntitySettings']
        if not entities or len({e.block for e in entities})!=1:return
        entity_type=self.library.types[entities[0].type_id]
        if entity_type.size!=32 or not any(m.offset==24 and m.atom==0 and m.storage==6 for m in entity_type.members):return
        for entry in self.entries:
            typ=self.library.types.get(entry.type_id)
            if not typ or typ.name!='EntityNetworkData' or typ.size!=8:continue
            if [(m.offset,m.size,m.atom,m.storage) for m in typ.members]!=[(0,4,0,6),(4,4,0,6)]:continue
            key,index=struct.unpack_from('<II',self.payload(entry.block),entry.offset)
            if index>=len(entities):continue
            target=entities[index]
            object_id=struct.unpack_from('<I',self.payload(target.block),target.offset+24)[0]
            if key!=object_id or key in (0,0xffffffff) or not (target.named or target.mapped):continue
            entry.label=f'{friendly(typ.name)} — {target.label} [object 0x{key:08X}; entity slot {index}]'
            entry.named=target.named
            entry.mapped=True

    def payload(self,block):
        if (block,0) in self.data.replacements:return self.data.replacements[block,0]
        if block not in self._payloads:self._payloads[block]=self.data.payload(block,0)
        return self._payloads[block]

    def array(self,block,base,member):
        payload=self.payload(block)
        if member.atom==1:
            if base+member.offset+16>len(payload):raise ValueError('Array descriptor outside payload')
            relative,count=struct.unpack_from('<qQ',payload,base+member.offset)
            if not count:return 0,0,0
            start=relative
        else:start=base+member.offset;count=member.info
        target=self.library.types.get(member.type_id)
        stride=target.size if member.storage==20 and target else struct.calcsize('<'+CODES[member.storage]) if member.storage in CODES else 8
        if count>100000 or stride<=0 or start<0 or start+count*stride>len(payload):raise ValueError('Array target/count outside payload')
        return start,count,stride

    def entry(self,block,offset,type_id,ordinal):
        typ=self.library.types[type_id];payload=self.payload(block)
        label=friendly(typ.name);name=None
        if typ.name=='DestructionHashEntry' and typ.size==16 and not any(payload[offset:offset+16]):
            return Entry(block,offset,type_id,f'{label} — empty slot {ordinal+1}',False,True)
        if typ.name=='EntitySettings' and typ.size==32 and offset+32<=len(payload):
            key,pointer,count,object_id,padding=struct.unpack_from('<QqQII',payload,offset)
            # EntitySettings reference layout: resource, component descriptor,
            # game-object ID, padding. Unused hash-table buckets use sentinels.
            if not key and pointer==-1 and count==0 and object_id==0xffffffff and padding==0:
                return Entry(block,offset,type_id,f'{label} — empty slot {ordinal+1}',False,True)
            resource_member=next((m for m in typ.members if m.offset==0 and m.atom==0 and m.storage==7 and m.trusted and m.label=='Resource'),None)
            if key and resource_member and key not in resource_names():
                return Entry(block,offset,type_id,f'{label} — Resource 0x{key:016X} [mapped ID; name unknown]',False,True)
        if typ.name in ('ComponentIndexData','EntitySettings') and not any(payload[offset:offset+typ.size]):
            return Entry(block,offset,type_id,f'{label} — empty slot {ordinal+1}',False,True)
        if type_id==hdremix.KIT and offset+4<=len(payload):
            identity=struct.unpack_from('<I',payload,offset)[0]
            name=next((e['name'] for e in hdremix.SCHEMA['changes'] if e['definition']==identity),None)
        elif type_id==0x63CE0FEB and offset+4<=len(payload):
            name=editor_names.PASSIVE_NAMES.get(struct.unpack_from('<I',payload,offset)[0])
        elif typ.name=='ComponentIndexData' and offset+8<=len(payload):
            key=struct.unpack_from('<Q',payload,offset)[0]
            name=resource_names().get(key)
            if not name and key:
                return Entry(block,offset,type_id,f'{label} — Resource 0x{key:016X} [mapped ID; name unknown]',False,True)
        elif typ.name.endswith('HashEntry') and typ.members and typ.members[0].offset==0 and typ.members[0].atom==0 and typ.members[0].storage==7 and offset+8<=len(payload):
            key=struct.unpack_from('<Q',payload,offset)[0]
            name=resource_names().get(key)
            if not name:
                return Entry(block,offset,type_id,f'{label} — Hash 0x{key:016X} [mapped ID; name unknown]',False,True)
        if not name:
            # An exact 64-bit dictionary match is useful even when the stripped
            # member label is unknown. Describe it as a resource association;
            # this does not establish the member's meaning or enable editing.
            resources=[]
            for member in typ.members:
                if member.atom!=0 or member.storage!=7 or offset+member.offset+8>len(payload):continue
                key=struct.unpack_from('<Q',payload,offset+member.offset)[0]
                candidate=resource_names().get(key) if key else None
                if candidate:resources.append(candidate)
            if resources:name='Resource: '+', '.join(dict.fromkeys(resources))
        if not name:
            for member in typ.members:
                if member.atom!=0 or member.storage!=18 or offset+member.offset+8>len(payload):continue
                pointer=struct.unpack_from('<q',payload,offset+member.offset)[0]
                if pointer<0 or pointer>=len(payload):continue
                end=payload.find(b'\0',pointer,min(pointer+512,len(payload)))
                if end<0:continue
                try:candidate=payload[pointer:end].decode('utf-8')
                except UnicodeDecodeError:continue
                if len(candidate)>=3 and candidate.isprintable():name=friendly(candidate);break
        if not name:
            for member in typ.members:
                if member.ordinal==0 and member.atom==0 and member.storage in CODES and member.type_id in self.library.enums and member.offset+offset+member.size<=len(payload):
                    value=struct.unpack_from('<'+CODES[member.storage],payload,offset+member.offset)[0]
                    candidate=self.library.enums[member.type_id].get(value)
                    if candidate and known_label(candidate):name=candidate;break
        if name:return Entry(block,offset,type_id,label+' — '+name,True)
        for member in typ.members:
            if not (member.trusted and member.atom==0 and member.storage==7 and
                    member.label in ('Resource','EntityPath','Type','Path','Name') and offset+member.offset+8<=len(payload)):continue
            key=struct.unpack_from('<Q',payload,offset+member.offset)[0]
            if key:
                return Entry(block,offset,type_id,f'{label} — {friendly(member.label)} 0x{key:016X} [mapped ID; name unknown]',False,True)
        # Enum identities come from the installed schema, including when its
        # value names are stripped. Keep the declared type and numeric value so
        # related records can be matched without inventing a gameplay name.
        identities=[]
        for member in typ.members:
            if member.atom!=0 or member.type_id not in self.library.enum_values or member.storage not in CODES:continue
            code=CODES[member.storage]
            if offset+member.offset+struct.calcsize('<'+code)>len(payload):continue
            value=struct.unpack_from('<'+code,payload,offset+member.offset)[0]
            if value not in self.library.enum_values[member.type_id]:continue
            enum_name=self.library.names.get(member.type_id,f'Enum 0x{member.type_id:08X}')
            resolved=self.library.enums.get(member.type_id,{}).get(value)
            identities.append(f'{friendly(enum_name)}={resolved or value}')
            if len(identities)==2:break
        if identities:
            return Entry(block,offset,type_id,label+' — '+' / '.join(identities)+' [mapped identity]',False,True)
        # A collection container has a structural role, not a missing item name.
        if offset==0 and len(typ.members)<=2 and any(m.atom in (1,2) for m in typ.members):
            return Entry(block,offset,type_id,f'{label} — collection [block {block+1}]',False,True)
        return Entry(block,offset,type_id,f'{label} — entry {ordinal+1} [name unresolved]',False)

    def properties(self,entry,limit=2500):
        result=[];payload=self.payload(entry.block)
        def add(offset,code,label,trusted,enum_type=0):
            width=struct.calcsize('<'+code)
            if offset<0 or offset+width>len(payload):raise ValueError('Scalar outside payload')
            value=struct.unpack_from('<'+code,payload,offset)[0]
            # Identifiers and references are displayed and resolved, but are not
            # presented as gameplay stats that can safely be changed in isolation.
            leaf=re.sub(r'\[\d+\]','',label.split('.')[-1]).lower()
            reference=(leaf in ('id','type','body type','name','name upper','name cased','description','archive','path','resource','index','icon')
                       or leaf.endswith((' id',' icon')) or 'path' in leaf or 'hash' in leaf
                       or entry.type_id==0x63CE0FEB and leaf=='passive bonus' and offset==entry.offset)
            note='' if trusted else 'Name unresolved; use Data Decoder for raw editing'
            if enum_type in self.library.enums:
                resolved=self.library.enums[enum_type].get(value)
                if resolved:note=(note+'; ' if note else '')+resolved
            if reference:note=(note+'; ' if note else '')+'Identifier/reference'
            if code=='Q' and value in resource_names():
                note+=(('; ' if note else '')+'Resource: '+resource_names()[value])
            if leaf=='modifier id' and value in editor_names.MOD_NAMES:note+=' — '+editor_names.MOD_NAMES[value]
            result.append(Property(entry.block,offset,code,label,value,trusted and not reference,enum_type,note))
        def walk(type_id,base,prefix,trail=()):
            if len(result)>=limit:return
            if len(trail)>16 or (type_id,base) in trail:raise ValueError('Recursive schema path')
            typ=self.library.types.get(type_id)
            if not typ:return
            if typ.flags&4:
                result.append(Property(entry.block,base,None,prefix+'Union','active member unresolved',False,note='Union interpretation requires additional schema knowledge'))
                return
            for member in typ.members:
                if len(result)>=limit:return
                label=prefix+self.library.member_name(member);offset=base+member.offset
                if member.atom in (1,2):
                    start,count,stride=self.array(entry.block,base,member)
                    if count>128:
                        result.append(Property(entry.block,offset,None,label,count,False,note='Collection: select its records in Entries'))
                        continue
                    for i in range(count):
                        path=prefix+friendly(member.element_labels[i])+'.' if member.element_labels else label+f'[{i}].'
                        child=self.library.types.get(member.type_id)
                        if child and child.name in ('HelldiverCustomizationPassiveBonusModifier','HelldiverCustomizationPassiveBonusStat') and stride>=4:
                            effect=editor_names.MOD_NAMES.get(struct.unpack_from('<I',payload,start+i*stride)[0])
                            if effect:path=label+f'[{i}] — {effect}.'
                        if member.storage==20:walk(member.type_id,start+i*stride,path,trail+((type_id,base),))
                        elif member.storage in CODES:add(start+i*stride,CODES[member.storage],path.rstrip('.'),member.trusted,member.type_id)
                        else:result.append(Property(entry.block,start+i*stride,None,path.rstrip('.'),'reference',False,note='Reference array retained unchanged'))
                elif member.atom==0 and member.storage==20:
                    walk(member.type_id,offset,label+'.',trail+((type_id,base),))
                elif member.atom==0 and member.storage in CODES:
                    add(offset,CODES[member.storage],label,member.trusted,member.type_id)
                elif member.atom==3:
                    result.append(Property(entry.block,offset,None,label,'bit field',False,note='Unresolved bit-field semantics'))
                elif member.atom==0 and member.storage==18:
                    if offset+8>len(payload):raise ValueError('String descriptor outside payload')
                    pointer=struct.unpack_from('<q',payload,offset)[0]
                    end=payload.find(b'\0',pointer,min(pointer+4096,len(payload))) if 0<=pointer<len(payload) else -1
                    value=payload[pointer:end].decode('utf-8',errors='replace') if end>=0 else '(none / unresolved)'
                    result.append(Property(entry.block,offset,None,label,value,False,note='String reference retained unchanged'))
                else:
                    result.append(Property(entry.block,offset,None,label,'reference',False,note='Pointer/string reference retained unchanged'))
        try:walk(entry.type_id,entry.offset,'')
        except (ValueError,struct.error,KeyError) as exc:
            result.append(Property(entry.block,entry.offset,None,'Unsupported nested layout',str(exc),False,note='No inferred offsets are edited'))
        return result

    def edit(self,prop,text):
        if not prop.editable or not prop.code:raise ValueError('This field is unresolved or is a reference; named editing is disabled.')
        value=float(text) if prop.code in ('f','d') else int(text,0) if text.lower().startswith(('0x','-0x')) else int(text)
        if prop.code in ('f','d') and not math.isfinite(value):raise ValueError('New value must be finite.')
        allowed=self.library.enum_values.get(prop.enum_type)
        if allowed is not None and value not in allowed:raise ValueError('Value is not defined by the installed enum schema.')
        payload=bytearray(self.payload(prop.block))
        struct.pack_into('<'+prop.code,payload,prop.offset,value)
        self.data.replace(prop.block,0,bytes(payload),float_offsets=[prop.offset] if prop.code=='f' and prop.offset%4==0 else [])

    def validate_footer_layout(self):
        index=len(self.data.resources)-1
        resource=self.data.resources[index];typ=self.library.types.get(resource.type_hash)
        if not typ or not typ.flags&1 or not any(m.atom==1 for m in typ.members):
            raise ValueError('Schema footer requires a variable-sized final block with declared dynamic arrays.')
        payload=self.payload(index);visited=set()
        def check(identity,offset):
            key=(identity,offset)
            if key in visited:return
            visited.add(key)
            if len(visited)>200000:raise ValueError('Schema validation traversal limit exceeded.')
            target=self.library.types.get(identity)
            if not target or target.flags&4 or offset<0 or offset+target.size>len(payload):raise ValueError('Unsupported final-block struct or union.')
            for member in target.members:
                if member.atom in (1,2):
                    start,count,stride=self.array(index,offset,member)
                    if member.storage==20:
                        for row in range(count):check(member.type_id,start+row*stride)
                elif member.atom==0 and member.storage==20:check(member.type_id,offset+member.offset)
                elif member.atom==0 and member.storage in (18,19):
                    pointer=struct.unpack_from('<q',payload,offset+member.offset)[0]
                    if pointer not in (-1,0) and not 0<=pointer<len(payload):raise ValueError('Final-block reference outside payload.')
        check(resource.type_hash,0)

    def prepare(self,allow_footer=False):
        if not self.data.replacements:return self.data.sealed,[]
        if not self.armor and not allow_footer:return self.data.prepare()
        if not self.armor:self.validate_footer_layout()
        else:hdremix.armor_headers(self.data.plain)
        candidate=bytearray(self.data.plain)
        for (index,_),payload in self.data.replacements.items():
            start=self.data.resources[index].offsets[0];candidate[start:start+len(payload)]=payload
        if self.armor:
            plain=finish_armor(self.data.plain,candidate,self.data.headers)
            hdremix.armor_headers(plain)
        else:
            plain=correct_reserved(self.data.plain,candidate,self.data.headers)
            if plain is None:plain=finish_tail(self.data.plain,candidate,self.data.headers)
        if content_hash(plain)!=content_hash(self.data.plain):raise ValueError('Hash mismatch')
        for pos,_,size in self.data.headers:
            if plain[pos+24:pos+24+size]!=candidate[pos+24:pos+24+size]:raise ValueError('Unexpected payload change')
        sealed=core.seal(plain)
        if core.unseal(sealed)!=plain:raise ValueError('Reseal mismatch')
        return sealed,[]
