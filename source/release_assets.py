"""Choose a published tool ZIP even when its download filename changes."""
def choose_zip(release,expected,keywords):
    assets=[a for a in release.get('assets',[]) if a.get('state') in ('uploaded',None)
            and str(a.get('name','')).lower().endswith('.zip')]
    exact=[a for a in assets if a['name'].casefold()==expected.casefold()]
    if len(exact)==1:return exact[0]
    usable=[a for a in assets if not any(word in a['name'].casefold() for word in ('source','symbols','debug'))]
    if usable:
        score=lambda a:sum(word in a['name'].casefold() for word in keywords)
        best=max(map(score,usable));matches=[a for a in usable if score(a)==best]
        if len(matches)==1:return matches[0]
    raise ValueError('The release has no unambiguous installable ZIP. Use the manual import button to choose the correct package.')
