"""Read-only native-editor coverage audit. Writes its report outside the game folder."""
import argparse
import hashlib
import json
from pathlib import Path

from game_schema import Library
from schema_document import Document


def audit(folder):
    folder=Path(folder)
    library=Library.open(folder/'dl_library.dl_typelib')
    result={'schema_sha256':hashlib.sha256((folder/'dl_library.dl_typelib').read_bytes()).hexdigest(),
            'types':len(library.types),'resolved_type_names':sum(not t.name.startswith('Unresolved') for t in library.types.values()),
            'member_definitions':sum(len(t.members) for t in library.types.values()),
            'verified_member_names':sum(m.trusted for t in library.types.values() for m in t.members),
            'note':'Names are recovered from reference layouts only when offsets, widths and types match. Unresolved fields remain read-only.',
            'files':[]}
    for path in sorted(folder.glob('generated_*.dl_bin')):
        row={'file':path.name}
        try:
            doc=Document(path,library)
            seen=set();sample_properties=[]
            for entry in doc.entries:
                if entry.type_id not in seen:
                    seen.add(entry.type_id);sample_properties.extend(doc.properties(entry))
            row.update(blocks=len(doc.data.resources),entries=len(doc.entries),resolved_entry_names=sum(e.named for e in doc.entries),
                       mapped_entries=sum(e.mapped and not e.named for e in doc.entries),
                       empty_slots=sum(' — empty slot ' in e.label for e in doc.entries),
                       unresolved_entries=sum(not e.named and not e.mapped for e in doc.entries),
                       representative_properties=len(sample_properties),representative_editable_properties=sum(p.editable for p in sample_properties),
                       layout_issues=doc.issues,
                       representative_layout_warnings=list(dict.fromkeys(str(p.value) for p in sample_properties if p.label=='Unsupported nested layout')))
            if doc.prepare()[0]!=doc.data.sealed:raise ValueError('Unmodified round trip changed the file')
            row['unmodified_roundtrip']='byte-identical'
        except Exception as exc:row['error']=str(exc)
        result['files'].append(row)
        print(path.name, row.get('entries','unsupported'), flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-data',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    folder=Path(args.game_data).resolve();output=Path(args.output).resolve()
    if output.is_relative_to(folder):raise SystemExit('Choose an output outside the game data directory.')
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(audit(folder),indent=2),encoding='utf-8')
