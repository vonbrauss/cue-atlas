import csv
import json
from pathlib import Path
from .metadata import FIELDS
from .timecode import format_tc,parse
COLUMNS=['Cue','Track','Status','Program In','Program Out','Duration TC','Duration Seconds','Elapsed In Seconds','Elapsed Out Seconds','Evidence Score','Reference File','Frame Rate','Project','Artist','Composer','Publisher','PRO','ISRC','ISWC','Copyright','License','Library','Catalog','Notes','Raw Metadata','Provider','Provider Track ID','Source URL','Version','Album Title','Catalog Code','Track Number','Rights Parties','Metadata Sources']

def export_reference_library(project,path):
    """Export every reference's stored cue-sheet metadata, including missing fields."""
    from .json_metadata import FORMAT,editable_values
    tracks=[]
    for track in project.tracks():
        metadata={field:'' for field in FIELDS}
        metadata.update({k:v for k,v in track['metadata'].items() if not k.startswith('_')})
        metadata.update(editable_values(track['metadata']))
        metadata.setdefault('raw',{})
        tracks.append({'reference_id':track['id'],'reference_file':track['path'],
                       'duration_seconds':track['duration'],'metadata':metadata,
                       'original_metadata':editable_values(track['metadata'])})
    data={'format':FORMAT,'schema_version':1,'project':project.get('name'),'tracks':tracks}
    Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return len(tracks)

def rows(project):
    settings=project.settings;rate=settings['rate'];origin=parse(settings['origin'],rate)
    tracks={t['id']:t for t in project.tracks()}
    for i,c in enumerate(project.included_cues(),1):
        t=tracks.get(c['track'],{});m=t.get('metadata',{})
        yield [i,m.get('title',c['title']) if t else c['title'],c['status'],
          format_tc(origin+c['start'],rate),format_tc(origin+c['end'],rate),format_tc(c['end']-c['start'],rate),
          round(c['end']-c['start'],6),round(c['start'],6),round(c['end'],6),c['confidence'] if t else '',
          t.get('path',''),rate,project.get('name'),*[m.get(f,'') for f in ['artist','composer','publisher','pro','isrc','iswc','copyright','license','library','catalog']],
          '; '.join(filter(None,[m.get('notes',''),c['note']])),json.dumps(m.get('raw',{}),ensure_ascii=False),
          *[m.get(f,'') for f in ['provider','provider_track_id','source_url','version','album_title','catalog_code','track_number']],
          json.dumps(m.get('parties',[]),ensure_ascii=False),json.dumps(m.get('provenance',[]),ensure_ascii=False)]
def safe(value):
    # Protect exports opened in spreadsheet programs from formula execution in imported tags.
    return "'"+value if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@','\t','\r')) else value

def export(project,path):
    data=[[safe(v) for v in r] for r in rows(project)]
    if Path(path).suffix.lower()=='.xlsx':
        from openpyxl import Workbook
        from openpyxl.styles import Font,PatternFill
        from openpyxl.utils import get_column_letter
        wb=Workbook();ws=wb.active;ws.title='Music cues';ws.append(COLUMNS)
        for row in data:ws.append(row)
        for cell in ws[1]:cell.font=Font(bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='173C3A')
        ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
        for i,title in enumerate(COLUMNS,1):ws.column_dimensions[get_column_letter(i)].width=min(44,max(14,len(title)+3))
        wb.save(path)
    else:
        with open(path,'w',newline='',encoding='utf-8-sig') as file:
            writer=csv.writer(file);writer.writerow(COLUMNS);writer.writerows(data)
