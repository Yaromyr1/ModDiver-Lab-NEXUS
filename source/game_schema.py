"""Read the installed DLTL schema; resolve labels only from verified layouts.

Binary layout reference: Filediver datalibrary/datalib.go (BSD-3-Clause).
Name dictionaries, reference Go layouts and license are in vendor/filediver.
The game's type library is read from the user's installation, never bundled.
"""
from dataclasses import dataclass,replace
from functools import lru_cache
from pathlib import Path
import re
import struct

import core

REFERENCE = Path(__file__).parent/'vendor/filediver'
CODES = {0:'b',1:'h',2:'i',3:'q',4:'B',5:'H',6:'I',7:'Q',8:'f',9:'d',
         10:'b',11:'h',12:'i',13:'q',14:'B',15:'H',16:'I',17:'Q'}
WIDTHS = {code:struct.calcsize('<'+code) for code in CODES.values()}


def name_hash(text):
    value=5381
    for char in text:value=(value*33+ord(char))&0xffffffff
    return (value-5381)&0xffffffff


def friendly(text):
    return re.sub(r'(?<=[a-z0-9])(?=[A-Z])',' ',text.replace('_',' ')).strip()


def known_label(text):
    return bool(text) and not re.search(r'(?i)^(unk|unknown|item\d|value_\d|property)',text)


@lru_cache(maxsize=1)
def references():
    names={}
    for line in (REFERENCE/'dl_type_names.txt').read_text(encoding='utf-8').splitlines():
        line=line.strip()
        if line and not line.startswith('//'):names[name_hash(line)]=line
    aliases={'int8':1,'uint8':1,'int16':2,'uint16':2,'int32':4,'uint32':4,'int64':8,'uint64':8,
             'float32':4,'float64':8,'bool':1,'JsonFloat':4,'DLHash':4,'stingray.Hash':8,'stingray.ThinHash':4,
             'DLArray':16,'DLString':8,'DLPtr':8,'mgl32.Vec2':8,'mgl32.Vec3':12,'mgl32.Vec4':16,'mgl32.Quat':16,'mgl32.Mat4':64}
    structs={};enums={}
    for path in sorted((REFERENCE/'datalibrary').rglob('*.go')):
        if path.name.endswith('_string.go'):continue
        text=path.read_text(encoding='utf-8')
        for name,base in re.findall(r'type\s+(\w+)\s+(u?int(?:8|16|32|64))\b',text):
            aliases[name]=aliases[base];aliases['enum.'+name]=aliases[base]
        for name,body in re.findall(r'type\s+(\w+)\s+struct\s*\{(.*?)\n\}',text,re.S):
            fields=[];valid=True
            for line in body.splitlines():
                line=line.split('//')[0].split('`')[0].strip()
                if not line:continue
                match=re.fullmatch(r'(\w+)\s+(\[\d+\])?([\w.]+)',line)
                if match:fields.append((match[1],(match[2] or '')+match[3]))
                elif re.fullmatch(r'[\w.]+',line):fields.append((line,line))
                else:valid=False;break
            if valid:structs[name]=fields
        for block in re.findall(r'const\s*\((.*?)\)',text,re.S):
            enum=None;mode=None;previous=None
            for ordinal,line in enumerate(x for x in (l.split('//')[0].strip() for l in block.splitlines()) if x):
                match=re.fullmatch(r'(\w+)(?:\s+(\w+))?(?:\s*=\s*(.*))?',line)
                if not match:continue
                label,declared,expression=match.groups()
                if declared:enum=declared
                if not enum:continue
                if expression:
                    if expression.strip()=='iota':mode='iota'
                    else:
                        try:previous=int(expression.strip(),0);mode='literal'
                        except ValueError:mode=None
                value=ordinal if mode=='iota' else previous if mode=='literal' else None
                if value is not None:
                    suffix=label.removeprefix(enum+'_')
                    if known_label(suffix):enums.setdefault(name_hash(enum),{})[value]=friendly(suffix)
    @lru_cache(maxsize=None)
    def layout(name,trail=()):
        if name in trail:raise ValueError('Recursive reference layout')
        if name in aliases:return aliases[name],[]
        arr=re.fullmatch(r'\[(\d+)\](.*)',name)
        if arr:return int(arr[1])*layout(arr[2],trail)[0],[]
        if name not in structs:raise ValueError('Unknown reference size')
        offset=0;result=[]
        for label,kind in structs[name]:
            size=layout(kind,trail+(name,))[0]
            result.append((offset,size,label,kind));offset+=size
        return offset,result
    candidates={}
    for name in structs:
        try:
            size,fields=layout(name)
            candidates.setdefault(name.removeprefix('raw').lower(),[]).append((size,fields,name))
        except ValueError:pass
    return names,candidates,enums


@dataclass
class Member:
    ordinal:int
    atom:int
    storage:int
    info:int
    type_id:int
    size:int
    offset:int
    label:str=''
    code:str|None=None
    trusted:bool=False
    element_labels:tuple=()


@dataclass
class Type:
    identity:int
    name:str
    size:int
    members:list
    flags:int=0


class Library:
    def __init__(self, data):
        if data[:4]!=b'LTLD' or len(data)<36:raise ValueError('Not a DLTL type library.')
        _,version,nt,ne,nm,nv,na,defaults,strings=struct.unpack_from('<9I',data)
        if version!=4 or max(nt,ne,nm,nv,na)>1000000:raise ValueError('Unsupported type-library version/counts.')
        type_pos=36+4*(nt+ne);enum_pos=type_pos+36*nt;member_pos=enum_pos+32*ne
        value_pos=member_pos+72*nm;alias_pos=value_pos+16*nv;string_pos=alias_pos+8*na+defaults
        if string_pos+strings>len(data):raise ValueError('Truncated type library.')
        hashes=struct.unpack_from('<'+str(nt)+'I',data,36)
        self.names,self.go,self.enums=references();self.types={};self.enum_values={}
        def string(offset):
            if offset==0xffffffff or not strings or offset>=strings:return ''
            end=data.find(b'\0',string_pos+offset,string_pos+strings)
            return data[string_pos+offset:end].decode('utf-8') if end>=0 else ''
        for i,identity in enumerate(hashes):
            desc=struct.unpack_from('<9I',data,type_pos+i*36)
            if desc[7]+desc[6]>nm:raise ValueError('Invalid type member range.')
            name=self.names.get(identity) or string(desc[0]) or f'UnresolvedType_{identity:08X}'
            members=[]
            for j in range(desc[7],desc[7]+desc[6]):
                p=member_pos+j*72;atom,storage,info=struct.unpack_from('<BBH',data,p+12)
                values=struct.unpack_from('<10I',data,p+16)
                member=Member(j-desc[7],atom,storage,info,values[0],values[2],values[6],
                              string(struct.unpack_from('<I',data,p)[0]),CODES.get(storage))
                member.trusted=known_label(member.label)
                if member.offset+member.size>desc[3]:raise ValueError('Member outside type size.')
                members.append(member)
            for size,fields,go_name in self.go.get(name.lower(),[]):
                primitive={'int8':0,'int16':1,'int32':2,'int64':3,'uint8':4,'uint16':5,'uint32':6,'uint64':7,'float32':8,'JsonFloat':8,'float64':9}
                def compatible(member,kind):
                    vector=re.fullmatch(r'mgl32\.Vec([234])',kind)
                    if vector:return (member.atom==2 and member.storage==8 and member.info==int(vector[1])) or (member.atom==0 and member.storage==20 and member.type_id==name_hash('CApiVector'+vector[1]))
                    array=re.fullmatch(r'\[(\d+)\](.*)',kind)
                    if array:
                        if member.atom!=2 or member.info!=int(array[1]):return False
                        kind=array[2]
                    elif member.atom not in (0,1):return False
                    if kind in primitive:return (member.storage-10 if 10<=member.storage<=17 else member.storage)==primitive[kind]
                    if kind=='DLArray':return member.atom==1
                    if kind=='DLString':return member.storage==18
                    if kind in ('stingray.Hash','stingray.ThinHash','DLHash'):return member.storage==(7 if kind=='stingray.Hash' else 6)
                    canonical=kind.removeprefix('enum.').removeprefix('raw')
                    return member.type_id==name_hash(canonical)
                # Different-size reference structs may describe an earlier build.
                # Accept only the exact matching prefix, stopping at the first
                # offset/width/type mismatch; never shift later field names.
                usable=[field for field in fields if field[2]!='_']
                cursor=0
                for member in members:
                    if cursor>=len(usable):break
                    field=usable[cursor]
                    if member.atom==3 and field[0]==member.offset and field[1]==member.size:
                        # A Go bitfield byte represents multiple DL bit members.
                        # Keep those names unresolved, then resume at next offset.
                        if cursor+1<len(usable) and usable[cursor+1][0]>member.offset:
                            if not any(m.atom==3 and m.offset==member.offset and m.ordinal>member.ordinal for m in members):cursor+=1
                        continue
                    if (field[0]!=member.offset or field[1]!=member.size or not compatible(member,field[3])):
                        # Some reference readers split an inline array into named
                        # scalar members (Damage / DurableDamage, for example).
                        # Accept only a complete, contiguous and typed match.
                        group=usable[cursor:cursor+member.info] if member.atom==2 else []
                        code=CODES.get(member.storage)
                        width=WIDTHS.get(code,0)
                        scalar=replace(member,atom=0,size=width)
                        if (not width or len(group)!=member.info or not group or member.size!=width*member.info
                            or any(off!=member.offset+i*width or size!=width or not compatible(scalar,kind)
                                   for i,(off,size,label,kind) in enumerate(group))):break
                        member.element_labels=tuple(f[2] for f in group)
                        member.label=' / '.join(member.element_labels)
                        member.trusted=all(known_label(label) for label in member.element_labels)
                        cursor+=member.info
                        continue
                    member.label=field[2];member.trusted=known_label(member.label)
                    cursor+=1
                break
            self.types[identity]=Type(identity,name,desc[3],members,desc[1])
        for dimensions in (2,3,4):
            vector=self.types.get(name_hash('CApiVector'+str(dimensions)))
            if vector and vector.size==dimensions*4 and len(vector.members)==dimensions:
                for axis,member in zip('XYZW',vector.members):
                    if member.atom==0 and member.storage==8 and member.offset=='XYZW'.index(axis)*4:
                        member.label=axis;member.trusted=True
        # Narrow, layout-checked annotations from the bundled SHODAN editor.
        annotations={'WeaponDataComponent':({1232,1240},{356:('Ergonomics',8)}),
                     'StratagemInfo':({400},{4:('Id',6),80:('Uses',6),104:('CooldownSeconds',8)}),
                     'HelldiverCustomizationKit':({64},{4:('AvailabilityTag',6),28:('PassiveBonus',16)})}
        for name,(sizes,fields) in annotations.items():
            target=self.types.get(name_hash(name))
            if not target or target.size not in sizes:continue
            for member in target.members:
                if member.offset in fields:
                    label,storage=fields[member.offset]
                    if member.atom==0 and member.storage==storage and member.size==4:
                        member.label=label;member.trusted=True
        enum_hashes=struct.unpack_from('<'+str(ne)+'I',data,36+nt*4)
        for i,identity in enumerate(enum_hashes):
            desc=struct.unpack_from('<8I',data,enum_pos+i*32)
            if desc[4]+desc[3]>nv:raise ValueError('Invalid enum value range.')
            storage=desc[2]&255
            code=CODES.get(storage)
            if code not in ('b','h','i','q','B','H','I','Q'):raise ValueError('Unsupported enum storage.')
            width=WIDTHS[code];mask=(1<<(8*width))-1
            values=set()
            for j in range(desc[4],desc[4]+desc[3]):
                value=struct.unpack_from('<Q',data,value_pos+j*16+8)[0]&mask
                if code.islower() and value>>(8*width-1):value-=1<<(8*width)
                values.add(value)
            self.enum_values[identity]=values

        # Filediver's Body layout (armor_sets.go) bridges its public
        # CustomizationKitBodyType spelling to the installed DL enum. Require
        # the complete type/pieces descriptor layout before sharing its names.
        body_enum=name_hash('HelldiverCustomizationBodyType')
        pieces=self.types.get(name_hash('HelldiverBodyTypePieces'))
        if (pieces and pieces.size==24 and len(pieces.members)==2
            and [(m.offset,m.size,m.atom,m.storage,m.type_id) for m in pieces.members]==[
                (0,4,0,16,body_enum),(8,16,1,20,name_hash('HelldiverCustomizationPieceInfo'))]
            and self.enum_values.get(body_enum)=={0,1,2,3}):
            public=self.enums.get(name_hash('CustomizationKitBodyType'),{})
            if public=={0:'Body Type Stocky',1:'Body Type Slim',2:'Body Type Unk',3:'Body Type Any'}:
                self.enums=dict(self.enums)
                self.enums[body_enum]={0:'Stocky',1:'Slim',3:'Any'}
                for target in (pieces,self.types.get(name_hash('HelldiverBody'))):
                    if not target:continue
                    for member in target.members:
                        if (member.offset,member.size,member.atom,member.storage,member.type_id)==(0,4,0,16,body_enum):
                            member.label='BodyType';member.trusted=True

    @classmethod
    def open(cls,path):
        data=Path(path).read_bytes()
        return cls(data if data[:4]==b'LTLD' else core.unseal(data))

    def type_name(self,identity):
        return friendly(self.names.get(identity,f'UnresolvedType_{identity:08X}'))

    def member_name(self,member):
        if member.label:return friendly(member.label)
        target=self.types.get(member.type_id)
        if target and member.atom in (1,2):return friendly(target.name)+' entries'
        return f'Unresolved property {member.ordinal+1}'
