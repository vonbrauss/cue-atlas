"""Zoomable cue editor. Edits are emitted only after a completed handle drag."""
import hashlib
from PySide6.QtCore import Qt,Signal,QRectF,QThread,QTimer
from PySide6.QtGui import QColor,QPainter,QPen
from PySide6.QtWidgets import QWidget,QMenu
from .project import trim_rows
from .audio import decode,waveform,Cancelled
from .timecode import format_tc,parse,RATES


class WaveformWorker(QThread):
    ready=Signal(object,object)
    def __init__(self,path,key,bins,parent):
        super().__init__(parent);self.path=path;self.key=key;self.bins=bins
    def run(self):
        try:
            audio=decode(self.path,start=self.key[0],duration=self.key[1],cancel=self.isInterruptionRequested)
            if not self.isInterruptionRequested():self.ready.emit(self.key,waveform(audio,self.bins))
        except (Cancelled,OSError,ValueError):pass


class Timeline(QWidget):
    seek=Signal(float);selectionChanged=Signal(object);boundaryChanged=Signal(str,float,float)
    editPointChanged=Signal(str,str,float,str)
    dragStarted=Signal()
    shuttleRequested=Signal(int)
    cueDrawn=Signal(float,float);boundaryFocused=Signal(object);nudgeRequested=Signal(int);auditionRequested=Signal()
    previewRequested=Signal();mergeRequested=Signal();reviewRequested=Signal();excludeRequested=Signal();addRequested=Signal();removeRequested=Signal()
    playCueRequested=Signal();identifyRequested=Signal()
    splitRequested=Signal()
    separationRequested=Signal()
    rangeChanged=Signal();rangeSeparationRequested=Signal()
    trimToPlayheadRequested=Signal(str)
    viewChanged=Signal(float,float)
    COLORS=['#75e6bd','#a7a0ff','#ffba77','#70ccff','#f18ec9']
    def __init__(self):
        super().__init__();self.setMinimumHeight(210);self.setFocusPolicy(Qt.StrongFocus);self.setMouseTracking(True)
        self.values=[];self.cues=[];self.duration=0;self.position=0;self.selected=set();self.current_id=None
        self.view_start=0;self.view_span=0;self.rate='29.97 DF';self.origin='01:00:00;00';self.editable=True
        self.show_excluded=False;self.drag=None;self.path=None;self.revision=None;self.detail=None;self.detail_key=None;self.worker=None
        self.active_edit=None;self.hover_pair=None;self.follow_enabled=True;self.snap_enabled=True
        self.hovered=None;self.follow_suspended=False;self.mark_in=None;self.mark_out=None;self.markers=[]
        self.source_identity=None;self.ai_regions=[];self.cue_colors={}
        self.detail_timer=QTimer(self);self.detail_timer.setSingleShot(True);self.detail_timer.setInterval(180);self.detail_timer.timeout.connect(self.load_detail)
    def set_source(self,path,duration,revision=None,identity=None):
        key=identity if identity is not None else (path,duration,revision)
        changed=key!=self.source_identity;monitor_changed=path!=self.path or revision!=self.revision
        self.source_identity=key
        self.path=path;self.duration=duration;self.revision=revision
        if monitor_changed:self.detail=None;self.detail_key=None;self.detail_timer.start()
        if changed:
            self.cue_colors={}
            self.mark_in=None;self.mark_out=None
            self.follow_suspended=False
            self.detail=None;self.detail_key=None;self.drag=None;self.active_edit=None;self.selected=set();self.current_id=None
            self.view_start=0;self.view_span=duration
            self.set_view(0,duration)
    def set_view(self,start,span):
        if not self.duration:
            self.viewChanged.emit(0,0);self.update();return
        self.view_span=min(self.duration,max(min(.25,self.duration),span))
        self.view_start=max(0,min(self.duration-self.view_span,start))
        self.viewChanged.emit(self.view_start,self.view_span);self.update();self.detail_timer.start()
    def zoom(self,factor,anchor=None):
        if not self.duration or self.drag:return
        # The cursor is the playhead, even after hovering elsewhere or panning away.
        anchor=max(0,min(self.duration,self.position if anchor is None else anchor))
        span=min(self.duration,max(min(.25,self.duration),self.view_span/factor))
        self.set_view(anchor-span/2,span)
    def follow_playhead(self,direction=1):
        """Page near the edge, leaving a little of the preceding view visible."""
        if not self.follow_enabled or self.follow_suspended or self.drag or not self.duration or self.view_span>=self.duration:return
        start=self.view_start;span=self.view_span;position=self.position
        outside=position<start or position>start+span
        if direction<0:
            if not outside and position>start+.08*span:return
            target=position-.88*span
        else:
            if not outside and position<start+.92*span:return
            target=position-.12*span
        target=max(0,min(self.duration-span,target))
        if abs(target-start)>1e-8:self.set_view(target,span)
    def fit_selection(self):
        cues=[c for c in self.cues if c['id'] in self.selected]
        if cues:
            start=min(c['start'] for c in cues);end=max(c['end'] for c in cues);pad=max(.1,(end-start)*.15)
            self.set_view(start-pad,end-start+2*pad)
    def load_detail(self):
        if self.worker is not None:
            self.worker.requestInterruption();return
        if not self.path or self.view_span>=self.duration:return
        key=(self.view_start,self.view_span,self.path,self.revision)
        if self.detail_key==key:return
        self.worker=WaveformWorker(self.path,key,max(100,self.width()*2),self)
        self.worker.ready.connect(self.detail_ready);self.worker.finished.connect(self.detail_finished);self.worker.start()
    def detail_ready(self,key,values):
        if key==(self.view_start,self.view_span,self.path,self.revision):self.detail_key=key;self.detail=values;self.update()
    def detail_finished(self):
        worker=self.worker;self.worker=None;worker.deleteLater()
        if self.detail_key!=(self.view_start,self.view_span,self.path,self.revision):
            # Retry only when the viewport changed while the worker was running.
            if worker.key!=(self.view_start,self.view_span,self.path,self.revision):self.detail_timer.start()
    def shutdown(self):
        self.detail_timer.stop()
        if self.worker:
            self.worker.requestInterruption();self.worker.wait()
    def x_at(self,seconds):return 12+(seconds-self.view_start)/max(self.view_span,1e-9)*max(1,self.width()-24)
    def time_at(self,x):return max(0,min(self.duration,self.view_start+(x-12)/max(1,self.width()-24)*self.view_span))
    def visible_cues(self):return [c for c in self.cues if bool(c.get('excluded'))==self.show_excluded]
    def cue_band_bottom(self):return 28+max(24,(self.height()-40)*.42)
    def regions(self):
        lanes=[];regions=[]
        for c in sorted(self.visible_cues(),key=lambda c:(c['start'],c['end'])):
            lane=next((i for i,end in enumerate(lanes) if end<=c['start']+1e-8),len(lanes))
            if lane==len(lanes):lanes.append(c['end'])
            else:lanes[lane]=c['end']
            if c['end']>=self.view_start and c['start']<=self.view_start+self.view_span:
                regions.append((c,lane))
        height=(self.cue_band_bottom()-28)/max(1,len(lanes))
        frozen=self.drag.get('rows',{}) if self.drag else {}
        return [(c,QRectF(self.x_at(c['start']),frozen.get(c['id'],(28+lane*height,height-3))[0],max(1,self.x_at(c['end'])-self.x_at(c['start'])),max(1,frozen.get(c['id'],(0,height-3))[1]))) for c,lane in regions]
    def color(self,c):
        if c.get('excluded'):return QColor('#7d8c94')
        if not c.get('track'):return QColor('#f5d65c')
        key=c['track']
        if key not in self.cue_colors:
            used=set(self.cue_colors.values());seed=int(hashlib.sha256(key.encode()).hexdigest()[:8],16)
            for offset in range(len(self.COLORS)):
                candidate=self.COLORS[(seed+offset)%len(self.COLORS)]
                if candidate not in used:break
            else:
                # Generate further distinct colors while keeping the yellow band reserved.
                hue=(seed%100000)/100000
                while True:
                    hue=(hue+.38196601125)%1
                    degrees=hue*320+80
                    candidate=QColor.fromHsvF((degrees%360)/360,.48,.94).name()
                    if candidate not in used:break
            self.cue_colors[key]=candidate
        return QColor(self.cue_colors[key])
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);p.fillRect(self.rect(),QColor('#121f25'))
        if not self.duration:
            p.setPen(QColor('#90a8aa'));p.drawText(self.rect(),Qt.AlignCenter,'No program waveform');return
        p.setClipRect(self.rect().adjusted(12,0,-12,0))
        key=(self.view_start,self.view_span,self.path,self.revision)
        detailed=self.detail is not None and self.detail_key==key
        values=self.detail if detailed else self.values
        waveform_top=self.cue_band_bottom()+8
        mid=(self.height()+waveform_top)/2;amplitude=max(1,(self.height()-waveform_top-12)/2)
        p.setPen(QColor('#29414a'));p.drawLine(12,int(waveform_top-4),self.width()-12,int(waveform_top-4))
        # Aggregate peaks to screen pixels so long programs paint in bounded time.
        begin=0 if detailed else int(self.view_start/self.duration*len(values))
        end=len(values) if detailed else min(len(values),int((self.view_start+self.view_span)/self.duration*len(values))+1)
        count=max(1,end-begin);width=max(1,self.width()-24)
        p.setPen(QPen(QColor('#70b6bc'),1))
        for x in range(width):
            a=begin+int(x/width*count);b=min(end,max(a+1,begin+int((x+1)/width*count)))
            peak=max(values[a:b],default=0);h=min(1,peak)*amplitude
            p.drawLine(x+12,int(mid-h),x+12,int(mid+h))
        for c,rect in self.regions():
            selected=c['id'] in self.selected;color=self.color(c);fill=QColor(color);fill.setAlpha(80 if selected else 38)
            p.setBrush(fill);p.setPen(QPen(color,2 if selected else 1));p.drawRoundedRect(rect,5,5)
            clipped=rect.intersected(QRectF(12,28,width,self.height()-28))
            if clipped.width()>24:
                p.save();p.setClipRect(clipped.adjusted(5,2,-5,-2));p.setPen(color)
                title=('Excluded · ' if c.get('excluded') else '')+c.get('display_title',c['title'])
                p.drawText(clipped.adjusted(8,5,-8,-5),Qt.AlignTop|Qt.AlignLeft,title);p.restore()
            if selected:
                for edge in (rect.left(),rect.right()):
                    p.fillRect(QRectF(edge-3,rect.top()+4,6,rect.height()-8),color)
                    p.setPen(QPen(color,1,Qt.DashLine))
                    p.drawLine(int(edge),int(self.cue_band_bottom()+4),int(edge),self.height())
            hover_edge=(self.hovered[1] if self.hovered and self.hovered[0]==c['id'] else None)
            if self.hover_pair and c['id'] in self.hover_pair:hover_edge='end' if c['id']==self.hover_pair[0] else 'start'
            if hover_edge and self.editable:
                edge=hover_edge;x=rect.left() if edge=='start' else rect.right()
                p.fillRect(QRectF(x+1 if edge=='start' else x-5,rect.top()+3,4,rect.height()-6),QColor('#ffffff'))
        p.setPen(QColor('#93aeb7'))
        for i in range(6):
            t=self.view_start+self.view_span*i/5;x=self.x_at(t)
            text=format_tc(parse(self.origin,self.rate)+t,self.rate)
            x=max(12,min(self.width()-105,x))
            p.drawText(int(x),18,text)
        for index,marker in enumerate(self.markers,1):
            point=marker['position']
            if not self.view_start<=point<=self.view_start+self.view_span:continue
            x=int(self.x_at(point));p.setPen(QPen(QColor('#92c9ff'),1,Qt.DotLine))
            p.drawLine(x,24,x,self.height());p.drawText(x+4,self.height()-8,f'{index} · {marker["text"][:35]}')
        for name,point in [('I',self.mark_in),('O',self.mark_out)]:
            if point is not None:
                x=self.x_at(point);p.setPen(QPen(QColor('#ffba77'),1,Qt.DashLine))
                p.drawLine(int(x),24,int(x),self.height());p.drawText(int(x)+4,40,name)
        if self.mark_in is not None and self.mark_out is not None:
            a,b=sorted((self.mark_in,self.mark_out));color=QColor('#70ccff');color.setAlpha(35)
            p.fillRect(QRectF(self.x_at(a),self.cue_band_bottom()+2,self.x_at(b)-self.x_at(a),self.height()-self.cue_band_bottom()-2),color)
        for a,b in self.ai_regions:
            p.fillRect(QRectF(self.x_at(a),self.height()-5,self.x_at(b)-self.x_at(a),4),QColor('#70ccff'))
        snapped=bool(self.drag and self.drag.get('snapped_to_playhead'))
        x=self.x_at(self.position);p.setPen(QPen(QColor('#79e2c4' if snapped else '#ffffff'),3 if snapped else 2));p.drawLine(int(x),24,int(x),self.height())
        if self.drag and self.drag.get('kind')=='draw':
            a,b=sorted((self.drag['anchor'],self.drag['position']))
            p.setPen(QPen(QColor('#ffffff'),2,Qt.DashLine));p.setBrush(QColor(117,230,189,55))
            p.drawRect(QRectF(self.x_at(a),28,max(1,self.x_at(b)-self.x_at(a)),self.cue_band_bottom()-28))
            p.drawText(20,self.height()-8,f'New cue · {b-a:.3f} s')
        elif self.drag and self.drag.get('kind')=='lasso':
            if self.drag['moved']:
                p.setPen(QPen(QColor('#92c9ff'),1,Qt.DashLine));p.setBrush(QColor(146,201,255,35))
                p.drawRect(QRectF(self.drag['anchor'],self.drag['position']).normalized())
        elif self.drag:
            c=next(c for c in self.cues if c['id']==self.drag['id'])
            value=c[self.drag['edge']];p.setPen(QColor('#ffffff'))
            side=self.drag.get('side')
            mode={'A':'A · left cue end','B':'B · right cue start','roll':'Roll A+B'}.get(side,self.drag['edge'].title())
            p.drawText(20,self.height()-8,f"{mode}  {format_tc(parse(self.origin,self.rate)+value,self.rate)}  ·  {value:.3f} s")
        elif self.hovered and self.editable:
            p.setPen(QColor('#ffffff'))
            p.drawText(20,self.height()-8,'Roll both sides' if self.hover_pair else ('Trim in' if self.hovered[1]=='start' else 'Trim out'))
    def shared_hit(self,pos):
        cues=sorted(self.cues,key=lambda c:(c['start'],c['end']));rects={c['id']:r for c,r in self.regions()}
        hits=[]
        for left,right in zip(cues,cues[1:]):
            if left.get('excluded') or right.get('excluded') or abs(left['end']-right['start'])>1e-8:continue
            a=rects.get(left['id']);b=rects.get(right['id'])
            if a is None or b is None or abs(a.top()-b.top())>1:continue
            if a.top()<=pos.y()<=a.bottom() and abs(pos.x()-self.x_at(left['end']))<=12:
                hits.append((abs(pos.x()-self.x_at(left['end'])),left,right))
        if hits:
            _,left,right=min(hits,key=lambda item:item[0]);return left,right
        return None
    def edit_target(self,pos):
        pair=self.shared_hit(pos)
        if pair:
            left,right=pair;delta=pos.x()-self.x_at(left['end'])
            side='roll' if abs(delta)<=3 else ('A' if delta<0 else 'B')
            return (right,'start',pair,side) if side=='B' else (left,'end',pair,side)
        c,edge=self.hit(pos)
        return c,edge,None,None
    def focus_boundary(self,c,edge,pair=None,side=None):
        self.active_edit={'id':c['id'],'edge':edge,'pair':tuple(item['id'] for item in pair) if pair else None,'side':side}
        self.boundaryFocused.emit(self.active_edit)
    def snapped_time(self,x):
        fps=RATES[self.rate][0]
        return max(0,min(self.duration,round(self.time_at(x)*fps)/fps))
    def drag_time(self,x,low,high):
        # Measure the dragged edge (including its grab offset), not the pointer.
        # A pixel-based radius gives the same feel at every timeline zoom level.
        radius=14 if self.drag.get('snapped_to_playhead') else 10
        snap=(self.snap_enabled and low<=self.position<=high
              and self.view_start<=self.position<=self.view_start+self.view_span
              and abs(x-self.x_at(self.position))<=radius)
        self.drag['snapped_to_playhead']=snap
        if snap:return self.position
        return max(low,min(high,self.snapped_time(x)))
    def begin_drag(self,c,edge,pair=None,side=None,grab_x=None):
        rows={item['id']:(r.top(),r.height()) for item,r in self.regions()}
        self.drag={'id':c['id'],'edge':edge,'start':c['start'],'end':c['end'],
                   'originals':{item['id']:(item['start'],item['end']) for item in self.cues},'rows':rows,
                   'snapshot':[dict(item) for item in self.cues],'grab_x':grab_x,'moved':False,
                   'offset':(grab_x-self.x_at(c[edge])) if grab_x is not None else 0}
        if pair:self.drag.update(pair=(pair[0]['id'],pair[1]['id']),side=side)
    def cancel_drag(self):
        if self.drag:
            if self.drag.get('kind')=='range':
                drag=self.drag;self.mark_in,self.mark_out=drag['marks'];self.selected=drag['selected'];self.current_id=drag['current_id'];self.drag=None
                self.selectionChanged.emit(list(self.selected));self.rangeChanged.emit();self.update();return
            if self.drag.get('kind')=='lasso':
                drag=self.drag;self.drag=None
                self.selected=set(drag['selected']);self.current_id=drag['current_id'];self.active_edit=drag['active_edit']
                self.selectionChanged.emit(list(self.selected));self.boundaryFocused.emit(self.active_edit);self.update();return
            self.cues=[dict(c) for c in self.drag['snapshot']]
            self.drag=None;self.update()
    def hit(self,pos):
        regions=self.regions()
        handles=[]
        for c,rect in regions:
            if rect.top()<=pos.y()<=rect.bottom():
                for edge,x in [('start',rect.left()),('end',rect.right())]:
                    if abs(pos.x()-x)<=9:handles.append((abs(pos.x()-x),c,edge))
        if handles:
            _,c,edge=min(handles,key=lambda item:item[0]);return c,edge
        for c,rect in reversed(regions):
            if rect.contains(pos):return c,None
        return None,None
    def select(self,c,modifiers):
        multi=bool(modifiers & (Qt.ControlModifier|Qt.MetaModifier|Qt.ShiftModifier))
        if multi:
            if modifiers & Qt.ShiftModifier and self.current_id:
                cues=self.visible_cues();ids=[item['id'] for item in cues]
                if self.current_id in ids:
                    a,b=sorted((ids.index(self.current_id),ids.index(c['id'])));self.selected.update(ids[a:b+1])
                else:self.selected.add(c['id'])
            elif c['id'] in self.selected:self.selected.remove(c['id'])
            else:self.selected.add(c['id'])
        else:self.selected={c['id']}
        self.current_id=c['id'];self.selectionChanged.emit(list(self.selected));self.update()
    def mousePressEvent(self,event):
        if event.button()!=Qt.LeftButton or not self.duration:return
        self.setFocus();c,edge,pair,side=self.edit_target(event.position())
        if self.editable and event.modifiers()==Qt.AltModifier:
            point=self.snapped_time(event.position().x())
            self.drag={'kind':'range','anchor':point,'marks':(self.mark_in,self.mark_out),'moved':False,'selected':set(self.selected),'current_id':self.current_id}
            self.selected=set();self.current_id=None;self.selectionChanged.emit([])
            self.mark_in=point;self.mark_out=point;self.dragStarted.emit();self.update();return
        if self.editable and event.modifiers()==Qt.ShiftModifier:
            self.drag={'kind':'draw','anchor':self.snapped_time(event.position().x()),'position':self.snapped_time(event.position().x()),
                       'grab_x':event.position().x(),'moved':False,'snapshot':[dict(item) for item in self.cues], 'click_cue':c}
            return
        if c:
            self.select(c,event.modifiers())
            if edge and self.editable and not event.modifiers():
                if side=='roll':
                    self.selected={item['id'] for item in pair};self.selectionChanged.emit(list(self.selected))
                self.focus_boundary(c,edge,pair,side)
                self.begin_drag(c,edge,pair,side,event.position().x())
            else:self.active_edit=None;self.boundaryFocused.emit(None)
        else:
            if event.modifiers() & Qt.ShiftModifier:
                self.active_edit=None;self.boundaryFocused.emit(None)
                self.selected=set();self.current_id=None;self.selectionChanged.emit([])
                self.seek.emit(self.time_at(event.position().x()));self.update();return
            self.drag={'kind':'lasso','anchor':event.position(),'position':event.position(),'moved':False,
                       'selected':set(self.selected),'current_id':self.current_id,'active_edit':self.active_edit,
                       'additive':bool(event.modifiers() & (Qt.ControlModifier|Qt.MetaModifier))}
    def mouseMoveEvent(self,event):
        if self.drag:
            if self.drag.get('kind')=='range':
                self.drag['moved']=True
                self.mark_in,self.mark_out=sorted((self.drag['anchor'],self.snapped_time(event.position().x())))
                self.update();return
            if self.drag.get('kind')=='lasso':
                drag=self.drag
                if not drag['moved']:
                    if (event.position()-drag['anchor']).manhattanLength()<3:return
                    drag['moved']=True;self.dragStarted.emit()
                    self.active_edit=None;self.boundaryFocused.emit(None)
                drag['position']=event.position()
                box=QRectF(drag['anchor'],drag['position']).normalized()
                selected={c['id'] for c,rect in self.regions() if box.intersects(rect)}
                if drag['additive']:selected.update(drag['selected'])
                changed=selected!=self.selected
                self.selected=selected
                self.current_id=drag['current_id'] if drag['current_id'] in selected else next((c['id'] for c in self.cues if c['id'] in selected),None)
                if changed:self.selectionChanged.emit([c['id'] for c in self.cues if c['id'] in selected])
                self.update();return
            if not self.drag['moved']:
                if self.drag['grab_x'] is not None and abs(event.position().x()-self.drag['grab_x'])<3:return
                self.drag['moved']=True;self.dragStarted.emit()
            if self.drag.get('kind')=='draw':
                self.drag['position']=self.snapped_time(event.position().x());self.update();return
            c=next((c for c in self.cues if c['id']==self.drag['id']),None)
            if c is None:return
            x=event.position().x()-self.drag['offset'];fps=RATES[self.rate][0]
            minimum=min(1/fps,self.drag['end']-self.drag['start'])
            if 'pair' in self.drag:
                left_id,right_id=self.drag['pair'];left=next(item for item in self.cues if item['id']==left_id);right=next(item for item in self.cues if item['id']==right_id)
                minimum=min(1/fps,self.drag['originals'][left_id][1]-left['start'],right['end']-self.drag['originals'][right_id][0])
                value=self.drag_time(x,left['start']+minimum,right['end']-minimum)
                if self.drag['side'] in ('A','roll'):left['end']=value
                if self.drag['side'] in ('B','roll'):right['start']=value
                self.update();return
            if self.drag['edge']=='start':c['start']=self.drag_time(x,0,c['end']-minimum)
            else:c['end']=self.drag_time(x,c['start']+minimum,self.duration)
            excluded={item['id'] for item in self.drag['snapshot'] if item.get('excluded')}
            self.cues=trim_rows(self.drag['snapshot'],c['id'],c['start'],c['end'],excluded,adjust_unknown=False)
            self.update();return
        c,edge,pair,side=self.edit_target(event.position())
        marker=next((m for m in self.markers if abs(self.x_at(m['position'])-event.position().x())<=7),None)
        self.setToolTip(marker['text'] if marker else '')
        self.hovered=(c['id'],edge) if c and edge else None
        self.hover_pair=tuple(item['id'] for item in pair) if side=='roll' else None
        drawing=bool(event.modifiers() & Qt.ShiftModifier)
        self.setCursor(Qt.CrossCursor if drawing else (Qt.SplitHCursor if side=='roll' else (Qt.SizeHorCursor if edge and self.editable else (Qt.PointingHandCursor if c else Qt.CrossCursor))))
        self.update()
    def leaveEvent(self,event):
        self.hovered=None;self.hover_pair=None;self.update()
        super().leaveEvent(event)
    def mouseReleaseEvent(self,event):
        if event.button()==Qt.LeftButton and self.drag:
            if self.drag.get('kind')=='range':
                self.mouseMoveEvent(event);self.drag=None;self.rangeChanged.emit();self.seek.emit(self.mark_in);self.update();return
            if self.drag.get('kind')=='lasso':
                self.mouseMoveEvent(event);drag=self.drag;self.drag=None
                if not drag['moved']:
                    self.active_edit=None;self.boundaryFocused.emit(None)
                    self.selected=set();self.current_id=None;self.selectionChanged.emit([])
                    self.seek.emit(self.time_at(event.position().x()))
                self.update();return
            if self.drag.get('kind')=='draw':
                drag=self.drag;self.cancel_drag()
                if drag['moved']:
                    a,b=sorted((drag['anchor'],drag['position']))
                    if b-a>=1/RATES[self.rate][0]-1e-8:self.cueDrawn.emit(a,b)
                elif drag['click_cue']:self.select(drag['click_cue'],Qt.ShiftModifier)
                return
            drag=self.drag;c=next(c for c in self.cues if c['id']==drag['id'])
            start,end=c['start'],c['end'];value=c[drag['edge']];self.cancel_drag()
            if (start,end)!=(drag['start'],drag['end']):
                if 'pair' in drag:self.editPointChanged.emit(*drag['pair'],value,drag['side'])
                else:self.boundaryChanged.emit(c['id'],start,end)
            self.update()
    def mouseDoubleClickEvent(self,event):
        c,_=self.hit(event.position())
        if c:self.cancel_drag();self.select(c,Qt.NoModifier);self.reviewRequested.emit()
    def wheelEvent(self,event):
        if self.drag:event.accept();return
        pixels=event.pixelDelta();angles=event.angleDelta()
        # macOS sends zero-delta begin/end events. Even zoom(1) recenters the view.
        if pixels.isNull() and angles.isNull():event.accept();return
        if event.modifiers() & (Qt.ControlModifier|Qt.MetaModifier):
            delta=pixels.y()/120 if pixels.y() else angles.y()/120
            self.zoom(1.3**delta)
        elif not pixels.isNull():
            delta=pixels.x() if abs(pixels.x())>=abs(pixels.y()) else pixels.y()
            self.pan(self.view_start-delta/max(1,self.width()-24)*self.view_span)
        elif angles.x():
            delta=pixels.x()/max(1,self.width()-24) if pixels.x() else angles.x()/120*.15
            self.pan(self.view_start-delta*self.view_span)
        elif event.modifiers() & Qt.ShiftModifier:
            delta=pixels.y()/max(1,self.width()-24) if pixels.y() else angles.y()/120*.15
            self.pan(self.view_start-delta*self.view_span)
        else:
            delta=pixels.y()/120 if pixels.y() else angles.y()/120
            self.zoom(1.3**delta)
        event.accept()
    def pan(self,start):
        self.follow_suspended=True
        self.set_view(start,self.view_span)
    def jump_edit(self,direction):
        points=sorted({c[edge] for c in self.visible_cues() for edge in ('start','end')})
        # QMediaPlayer rounds seeks to integer milliseconds. Treat that whole
        # millisecond as the current edit, otherwise repeated arrows get stuck.
        points=[p for p in points if (p-self.position)*direction>.001000001]
        if not points:return
        point=min(points) if direction>0 else max(points)
        self.follow_suspended=False
        self.seek.emit(point)
        if not self.view_start<=point<=self.view_start+self.view_span:
            self.set_view(point-self.view_span/2,self.view_span)
    def keyPressEvent(self,event):
        undo_key=event.key()==Qt.Key_Z and bool(event.modifiers() & Qt.ControlModifier) and not bool(event.modifiers() & Qt.ShiftModifier)
        if self.drag and (event.key()==Qt.Key_Escape or undo_key):
            self.cancel_drag();return
        if self.drag:return
        modifiers=event.modifiers() & ~Qt.KeypadModifier
        if modifiers in (Qt.NoModifier,Qt.ShiftModifier) and event.key() in (Qt.Key_Up,Qt.Key_Down):
            self.jump_edit(1 if event.key()==Qt.Key_Down else -1)
            event.accept();return
        if event.modifiers()==Qt.NoModifier and event.key() in (Qt.Key_Q,Qt.Key_W):
            if self.editable and not event.isAutoRepeat():
                self.trimToPlayheadRequested.emit('start' if event.key()==Qt.Key_Q else 'end')
            event.accept();return
        if event.modifiers()==Qt.NoModifier and event.key() in (Qt.Key_Delete,Qt.Key_Backspace):
            if self.editable and self.selected and not event.isAutoRepeat():self.removeRequested.emit()
            event.accept();return
        if event.modifiers() in (Qt.NoModifier,Qt.ShiftModifier):
            if event.key() in (Qt.Key_Space,Qt.Key_M) and not event.modifiers():
                if not event.isAutoRepeat():
                    (self.previewRequested if event.key()==Qt.Key_Space else self.mergeRequested).emit()
                return
            if not event.modifiers() and event.key() in (Qt.Key_J,Qt.Key_K,Qt.Key_L):
                if not event.isAutoRepeat():self.shuttleRequested.emit({Qt.Key_J:-1,Qt.Key_K:0,Qt.Key_L:1}[event.key()])
                return
            if not event.modifiers() and event.key() in (Qt.Key_Comma,Qt.Key_Period,Qt.Key_A):
                if event.key()==Qt.Key_A:self.auditionRequested.emit()
                else:self.nudgeRequested.emit(-1 if event.key()==Qt.Key_Comma else 1)
                return
        super().keyPressEvent(event)
    def contextMenuEvent(self,event):
        c,_=self.hit(event.pos())
        if c and c['id'] not in self.selected:self.select(c,Qt.NoModifier)
        menu=QMenu(self)
        menu.addAction('Play from cue start',self.playCueRequested.emit).setEnabled(bool(self.selected))
        menu.addAction('Identify selected cue…',self.identifyRequested.emit).setEnabled(self.editable and len(self.selected)==1)
        menu.addAction('Reduce dialogue and retry…',self.separationRequested.emit).setEnabled(self.editable and bool(self.selected))
        menu.addAction('AI separate marked range',self.rangeSeparationRequested.emit).setEnabled(self.editable and self.mark_in is not None and self.mark_out is not None and self.mark_out>self.mark_in)
        menu.addAction('Review cue…',self.reviewRequested.emit).setEnabled(self.editable and len(self.selected)==1)
        menu.addAction('Merge selected…',self.mergeRequested.emit).setEnabled(self.editable and len(self.selected)>1)
        menu.addAction('Split cue at playhead',self.splitRequested.emit).setEnabled(self.editable and len(self.selected)==1)
        menu.addAction('Restore' if c and c.get('excluded') else 'Exclude',self.excludeRequested.emit).setEnabled(self.editable and bool(self.selected))
        menu.addAction('Add cue at playhead…',self.addRequested.emit).setEnabled(self.editable)
        menu.addAction('Delete selected cues…',self.removeRequested.emit).setEnabled(self.editable and bool(self.selected))
        menu.exec(event.globalPos())
