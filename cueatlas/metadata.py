"""Preserve text tags, including RIFF INFO, BEXT and iXML; never infer rights."""
import re
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
import mutagen
FIELDS=['title','artist','composer','publisher','pro','isrc','iswc','copyright','license','library','catalog','notes',
        'provider','provider_track_id','source_url','version','album_title','catalog_code','track_number']
ALIASES={'title':['tit2','title','inam'], 'artist':['tpe1','artist','iart'],
 'composer':['tcom','composer','iwri','writer'], 'publisher':['tpub','publisher','ipub'],
 'pro':['pro','performingrightsorganization','performancerightsorganization'],
 'isrc':['tsrc','isrc'], 'iswc':['iswc'], 'copyright':['tcop','copyright','icop'],
 'license':['license','licence','licensing','licenseurl','wcop'],
 'library':['library','musiclibrary','label','organization'],
 'catalog':['catalog','catalogue','catalognumber','cataloguenumber','album','talb'],
 'notes':['comment','comments','description','icmt','bextdescription']}
# Credits remain associated with their parties; never infer a writer from an artist tag.
PRO_PATTERN=r'(?:ASCAP|BMI|SESAC|PRS|SACEM|SOCAN|GEMA|APRA|SGAE|SIAE|STIM|KODA|TONO|BUMA|SUISA|IMRO|SABAM|JASRAC|AMRA|GMR|BIEM)'

def xml_attributes(raw):
    """Read repeated Steinberg NAME/VALUE pairs without flattening them."""
    try:
        root=ET.fromstring(raw.get('iXML',''))
    except (ET.ParseError,TypeError):return {}
    attrs={}
    for element in root.iter():
        if element.tag.split('}')[-1]!='ATTR':continue
        children={c.tag.split('}')[-1]:(c.text or '').strip() for c in element}
        if children.get('NAME') and children.get('VALUE'):
            attrs[children['NAME']]=children['VALUE']
    return attrs


def credit_pieces(text):
    """Split credit lists outside brackets/quotes; internal slashes are names."""
    pieces=[];buffer=[];depth=0;quoted=False;i=0
    while i<len(text):
        char=text[i]
        if char=='"':
            if quoted and i+1<len(text) and text[i+1]=='"':buffer.append('"');i+=2;continue
            quoted=not quoted;i+=1;continue
        if not quoted:
            if char in '([':depth+=1
            elif char in ')]':depth=max(0,depth-1)
            slash=char=='/' and i>0 and i+1<len(text) and ((text[i-1].isspace() and text[i+1].isspace()) or text[i-1] in '%)]')
            if not depth and (char in ',;|\n\r' or slash):
                pieces.append(''.join(buffer).strip());buffer=[];i+=1;continue
        buffer.append(char);i+=1
    pieces.append(''.join(buffer).strip())
    # Retain the common single surname-first credit, e.g. Smith, John [PRS].
    # Quote names containing commas in longer lists to make boundaries explicit.
    if len(pieces)==2 and text.count(',')==1 and not any(c in text for c in ';|\n/"'):
        second=re.sub(r'\[[^]]*\]|\([^)]*\)|\d+(?:\.\d+)?\s*%','',pieces[1]).strip()
        if re.search(r'\[[^]]*\]|\([^)]*\)',pieces[1]) and len(pieces[0].split())==len(second.split())==1:pieces=[pieces[0]+', '+pieces[1]]
    return pieces


def parse_parties(text,role):
    parties=[]
    affiliation=r'[\[(]('+PRO_PATTERN+r'(?:\s*[/,&+]\s*'+PRO_PATTERN+r')*)[\])]'
    for piece in credit_pieces(text):
        piece=re.sub(r'^ORIGINAL PUB:\s*','',piece.strip(),flags=re.I)
        if not piece:continue
        society=re.search(affiliation,piece,re.I)
        share=re.search(r'(\d+(?:\.\d+)?)\s*%',piece)
        name=re.sub(affiliation,'',piece,flags=re.I)
        name=re.sub(r'\d+(?:\.\d+)?\s*%','',name).strip()
        if not name:continue
        parties.append({'role':role,'name':name,'pro':society.group(1).upper() if society else '',
                        'ipi':'','share_percent':float(share.group(1)) if share else None})
    return parties


def normalize(raw, filename):
    normalized={re.sub('[^a-z0-9]','',k.lower().split(':')[-1]):v for k,v in raw.items()}
    out={field:'' for field in FIELDS}
    for field,aliases in ALIASES.items():
        out[field]=next((str(normalized[a]) for a in aliases if normalized.get(a)), '')
    attrs=xml_attributes(raw)
    def first(*keys):return next((str(raw[k]).strip() for k in keys if raw.get(k)), '')
    out['title']=out['title'] or attrs.get('SmfSongName','') or Path(filename).stem
    out['library']=out['library'] or attrs.get('MediaLibrary','')
    out['album_title']=first('TALB','CDTITLE','IPRD') or attrs.get('MediaAlbum','')
    out['catalog']=out['catalog'] or out['album_title']
    out['catalog_code']=first('VOLUME')
    if not out['catalog_code']:
        code=re.search(r'\(([A-Z][A-Z0-9]*-\d+)\)',out['album_title'])
        if code:out['catalog_code']=code.group(1)
        elif re.fullmatch(r'[A-Z]+\d+_\d+',first('TOAL')):out['catalog_code']=first('TOAL').rsplit('_',1)[0]
    out['track_number']=first('TRCK','ITRK') or attrs.get('MediaTrackNumber','')
    out['provider_track_id']=first('SOURCE','TOAL')
    out['isrc']=out['isrc'] or first('isrcId').replace('-','')
    if 'APM Music' in str(raw.get('ICOP',''))+out['artist']+str(raw.get('bext_originator','')):
        out['provider']='APM Music'
        match=re.search(r'([A-Z0-9]+_[A-Z0-9]+_\d{3,}_\d{3,})(?=[_. -]|$)',Path(filename).stem)
        if match:out['provider_track_id']=out['provider_track_id'] or match.group(1)
    elif 'universalproductionmusic.com' in str(raw):out['provider']='Universal Production Music'
    elif 'VideoHelper' in str(raw):out['provider']='VideoHelper'
    if not out['library'] and out['provider'] in {'APM Music','Universal Production Music'}:
        out['library']=first('TPE2')
    # Preserve version wording without removing it from the supplied track title.
    version=re.search(r'\(([^)]*(?:instrumental|underscore|main|full|seconds|mix|stem)[^)]*)\)| - ((?:Full instrumental|Instrumental|Underscore|Main).*)$| (Instrumental)$',out['title'],re.I)
    if version:out['version']=next(g for g in version.groups() if g)
    out['parties']=parse_parties(out['composer'],'composer')+parse_parties(out['publisher'],'publisher')
    out['pro']=out['pro'] or '; '.join(dict.fromkeys(p['pro'] for p in out['parties'] if p['pro']))
    out['raw']=raw
    return out


def merge_parties(existing,candidate):
    """Fill known parties by role/name; never silently replace or add a party."""
    from copy import deepcopy
    if not existing:return deepcopy(candidate),[]
    merged=deepcopy(existing);conflicts=[]
    for party in candidate:
        matches=[p for p in merged if p.get('role')==party.get('role') and p.get('name','').strip().casefold()==party.get('name','').strip().casefold()]
        if len(matches)!=1:
            conflicts.append(party.get('name','unknown party'));continue
        target=matches[0]
        for key in ('pro','ipi','share_percent'):
            value=party.get(key)
            if value is None or value=='':continue
            if target.get(key) is not None and target.get(key)!='' and target[key]!=value:
                conflicts.append(f"{party['name']} {key}")
            else:target[key]=value
    return merged,conflicts


def fill_metadata(existing,candidate,source,source_url=''):
    """Fill blanks only, preserving edits and recording the origin of each change."""
    from copy import deepcopy
    from datetime import datetime,timezone
    result=deepcopy(existing);changed=[]
    parties,conflicts=merge_parties(existing.get('parties',[]),candidate.get('parties',[]))
    if not conflicts and parties!=existing.get('parties',[]) and parties:
        result['parties']=parties;changed.append('parties')
    for field in FIELDS:
        value=candidate.get(field)
        if not result.get(field) and value:
            result[field]=deepcopy(value);changed.append(field)
    if changed:
        result.setdefault('provenance',[]).append({'source':source,'source_url':source_url,
            'retrieved_at':datetime.now(timezone.utc).isoformat(),'status':'unverified','fields':changed})
    return result,changed

def read_metadata(path):
    raw={}; warnings=[]
    try:
        f=mutagen.File(path)
        if f and f.tags:
            for k,v in f.tags.items():
                if k.startswith(('APIC','PIC')): continue
                if hasattr(v,'text'): value='; '.join(map(str,v.text))
                elif isinstance(v,(list,tuple)): value='; '.join(map(str,v))
                else: value=str(v)
                if len(value)<65536: raw[str(k)]=value
    except Exception as e: warnings.append(str(e))
    if Path(path).suffix.lower() in {'.wav','.wave'}:
        try:
            with open(path,'rb') as file:
                header=file.read(12)
                if header[:4] in {b'RIFF',b'RF64'} and header[8:]==b'WAVE':
                    while True:
                        chunk=file.read(8)
                        if len(chunk)<8: break
                        key,size=struct.unpack('<4sI',chunk)
                        if key not in {b'LIST',b'bext',b'iXML'} or size>4_000_000:
                            file.seek(size+(size%2),1);continue
                        data=file.read(size);file.seek(size%2,1)
                        if key==b'LIST' and data[:4]==b'INFO':
                            pos=4
                            while pos+8<=len(data):
                                tag,n=struct.unpack('<4sI',data[pos:pos+8]);pos+=8
                                raw[tag.decode(errors='replace')]=data[pos:pos+n].rstrip(b'\0').decode('utf-8',errors='replace')
                                pos+=n+(n%2)
                        elif key==b'bext':
                            raw['bext_description']=data[:256].rstrip(b'\0').decode(errors='replace')
                            raw['bext_originator']=data[256:288].rstrip(b'\0').decode(errors='replace')
                            raw['bext_originator_reference']=data[288:320].rstrip(b'\0').decode(errors='replace')
                        elif key==b'iXML':
                            raw['iXML']=data.rstrip(b'\0').decode(errors='replace')
                            try:
                                for element in ET.fromstring(data.rstrip(b'\0')).iter():
                                    if element.text and element.text.strip(): raw[element.tag]=element.text.strip()
                            except ET.ParseError: pass
        except Exception as e: warnings.append(str(e))
    result=normalize(raw,path)
    result['import_warnings']=warnings
    result['provenance']=fill_metadata({},result,'embedded tags')[0].get('provenance',[])
    return result
