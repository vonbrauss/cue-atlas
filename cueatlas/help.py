from . import __version__

GUIDE = '''# Cue Atlas {version}

## Keyboard shortcuts at a glance

Click the waveform or cue sheet before using playback and navigation shortcuts. Click the waveform before using trim, audition, or nudge shortcuts. Text fields keep their normal typing behavior.

| Key | Action | Where |
| --- | --- | --- |
| Down | Seek to the next cue start or end | Waveform or cue sheet |
| Up | Seek to the previous cue start or end | Waveform or cue sheet |
| R | Go to the next cue needing review | Waveform or cue sheet |
| B | Add a marker comment at the playhead | Waveform or cue sheet |
| Left / Right | Step the playhead backward / forward one frame | Waveform or cue sheet |
| Shift+Left / Right | Move the playhead backward / forward one second | Waveform or cue sheet |
| Home / End | Go to program start / end | Waveform or cue sheet |
| I / O | Mark the start / end of a new cue | Waveform or cue sheet |
| N | Create a cue from the marked interval | Waveform or cue sheet |
| F | Identify the selected cue | Waveform or cue sheet |
| Enter | Review the selected cue | Waveform or cue sheet |
| X | Exclude / restore selected cues | Waveform or cue sheet |
| Escape | Cancel a drag; otherwise stop playback and clear marks / selection | Waveform or cue sheet |
| Backslash | Fit the entire program | Waveform or cue sheet |
| Q | Trim / extend the selected cue start to the playhead | Waveform |
| W | Trim / extend the selected cue end to the playhead | Waveform |
| J / K / L | Reverse / pause / forward; repeat J or L for faster playback | Waveform or cue sheet |
| Space | Preview selected cue or pause; free playback when no cue is selected | Waveform or cue sheet |
| A | Audition the selected boundary | Waveform |
| Comma / period | Nudge selected boundary backward / forward one frame | Waveform |
| M | Merge selected adjoining cues | Waveform or cue sheet |
| S | Split the selected cue at the playhead | Waveform or cue sheet |
| Delete / Backspace | Delete selected cues after confirmation | Waveform or cue sheet |
| Shift+Up / Down | Extend row selection | Cue sheet |
| Command/Ctrl-Z | Undo; cancel an unfinished drag | Editing workspace |
| Command/Ctrl-Shift-Z | Redo | Editing workspace |
| Command/Ctrl + / − | Zoom around the playhead | Main window |

Arrow navigation moves the playhead without changing cue selection. It skips the current boundary and stops at the first or last available edit; it does not wrap.

The keys in the written guide are defaults. **Edit → Keyboard shortcuts** lets you reassign or clear editor bindings. The shortcut reference displays your current assignments. Menu shortcuts and Shift+Up/Down row selection are reserved. Conflicts must be resolved before saving; **Restore Defaults** resets the editor keys. Assignments are remembered for this app installation and do not change normal text-field typing.

Left/Right stepping uses the project frame rate and pauses playback. Shift+Left/Right moves one second; Home/End goes to the program limits. These commands bring the playhead into view when needed. On compact Mac keyboards, Fn+Left/Right produces Home/End.

For a new cue, press **I** at its start and **O** at its end. Dashed I/O lines show the marks. Press **N** to save an Untitled cue and select it, then **F** to identify it or **Enter** to review it. Out must be at least one frame after In. Creating the cue clears both marks; Escape also clears them. Marks are temporary and reset when switching projects or changing source media. New cues can overlap existing cues and support Undo/Redo.

**X** excludes selected cues in the normal view. To restore, show **Excluded**, select the cue, and press X again. **Backslash** fits the whole program regardless of selection; the Fit button still fits selected cues when present.

## Editing and clearing credits

Reference search filters cached metadata as you type, without rereading files or recalculating duplicates for each letter. Library changes refresh the search data.

Composer and publisher fields in the metadata editor accept normal typing, Backspace, and Delete. Clearing a field removes its matching Rights parties entries when you leave the field or Save. Other parties are retained; matching names keep their IPI and share details. You can also edit or remove individual rows in Rights parties. Save applies the changes; Cancel leaves the stored reference unchanged. PRO affiliations remain editable per party in Rights parties.

## Library search and table sorting

The Reference library search sits between **Import library** and **Metadata**. Search matches reference metadata and file paths, regardless of letter case; clear the field to show all references. The count below the table shows visible and total references.

Click a column header in the cue sheet or Reference library to sort ascending; click again for descending. Times, durations, cue numbers, and evidence scores sort numerically. Sorting changes the view only; cue timing and reference assignments stay attached to their original entries. Cue numbers retain their original order; click **#** to restore chronological order.

Use the expand icon at the right of the Reference library toolbar, or **Library → Focus reference library**, to fill the workspace. Click the same icon to restore the waveform and tabs. Waveform, cue-sheet, and reference-library focus are mutually exclusive.

## Project setup
Create or open a project from **Project**. Add reference music in **Reference library**, or use **Import library** to copy references, fingerprints, and licensing metadata from a previous Cue Atlas project.

Choose program media, then analyze. WAV, AIFF, MP3, FLAC, M4A, MP4, MOV, and MXF are supported. Video is analyzed as audio only, using its first audio track. No video viewer is required. Files without an audio track cannot be analyzed. The audio timeline includes any leading audio offset; trailing video without audio does not create music cues.

After setup, use **Program** (the menu bar or the gear in the program header) to change/relink the source or analyze again. Project settings are available only in **Project → Project settings**. Reanalysis replaces the current cue sheet; use Project > Backup first to keep an earlier version. Project databases reference the original media; keep those files available.

## Manage projects
Open **Project → Browse projects** from the app dropdown or menu bar. The header dropdown and menu bar share the same commands, grouped into switching projects, the current project, and delivery. **Recent projects** shows the latest six; **Browse all projects** opens the full browser. Older entries stay in the browser until you remove them.

### Find your project

Choose **All projects**, **Favorites**, or **Unavailable** in the sidebar. Search by name or folder. Sort by **Recently opened**, **Name A–Z**, or **Name Z–A**. Each row shows the project location and availability, so projects with the same name are easy to distinguish.

Select a project and click **Favorite** to keep it in the Favorites collection. **Unfavorite** removes just the favorite mark. **Add existing…** registers another `.cueatlas` file without opening it. **New project…** creates and opens a new project.

Double-click a row or use **Open** to switch. Rename, Backup, Remove from Recents, and Move to Trash are grouped under **More**. There is no fixed project-count limit in the browser.

### Open and rename

**Open** switches projects. **Rename** changes both the project name and its `.cueatlas` filename in the same folder. The project name always matches the filename without the extension. Finder renames are reflected when opening a project; same-folder renames of the open project are detected automatically. Recents follows an open project’s renamed location. Existing destination files are never overwritten; failed in-app renames leave the original project usable. 

### Back up and locate

**Backup** creates a separate `.cueatlas` copy. **Open folder** opens its containing folder in Finder/the file manager.

### Manage recent projects

**More → Remove from Recents** removes its favorite mark and hides a listing without deleting anything or closing the current project. An open project remains visible in the manager until closed and is marked **Open · not in Recents**. **Project → Close project** closes the workspace without deleting its database.

### Move a project to Trash

**Move to Trash** asks for confirmation, with No as the default. It moves only the selected `.cueatlas` file, including its saved cues, reference fingerprints, and settings; original audio/video files and other projects remain in place.

The open project is closed before moving its database. If moving fails, the project is reopened. Missing or invalid project files can be removed from Recents but cannot be opened or trashed here. 

To restore a trashed project, restore its file through Finder/your file manager and open it again. Cue Undo cannot undo deleting a project. A backup contains project data and media links, not copies of source recordings.

## Workspace
Drag the divider between the waveform and cue sheet to resize them. The expand icon at the top right of either pane fills the workspace with that pane; click its restore icon to return. The app window stays fixed; long cue/reference lists scroll inside their tables. **Export cue sheet** stays at the top right in every view.

## Playback and zoom
- **L**: play forward from the current playhead. Repeat for 2×, 4×, or 8×.
- **K**: pause at the current position.
- **J**: play backward with audio. Repeat for 2×, 4×, or 8×.
- Changing direction returns to 1×. Reverse playback prepares short audio chunks; a brief preparation pause can occur at a chunk boundary.
- J/K/L work with the waveform or cue sheet focused. They do not intercept typing in text fields.
- **Space**: preview the selected cue from its head, or play freely from the cursor when no cue is selected. Press again to pause.
- Click below the cue overlays to deselect and place the playhead anywhere, including before a cue.
- **Command/Ctrl + / −**, the zoom buttons, and the mouse wheel zoom centered on the playhead cursor, including when it is outside the current view. Hovering elsewhere does not change the zoom target.
- **View → Follow playhead** is enabled by default. During forward playback the timeline pages ahead near the right edge, keeping a small overlap with the previous view. Reverse playback pages toward the left edge. Zoom stays unchanged. Disable it to hold the view while playing; your preference is remembered. Paused navigation and unfinished drags do not trigger automatic paging.
- Two-finger scrolling in either direction, Shift+wheel, and the scrollbar pan the timeline. Command/Ctrl+scroll zooms. Manual panning suspends playback follow until you seek or toggle Follow playhead, so playback does not pull the view back.
- **Fit** fits selected cues, or the full program with no selection. View also offers both commands.

## Cue editing

### Trim to the playhead

With the timeline focused, **Q** moves the selected cue’s start to the playhead and **W** moves its end. Inside the cue these trim; before the cue Q extends its start, and after the cue W extends its end. Select exactly one cue to extend. Neighbors keep their timings, overlaps are allowed, and Undo restores the edit. Without a selection, an unambiguous cue under the playhead can still be trimmed.

**Option/Alt-I** clears In, **Option/Alt-O** clears Out, and **Option/Alt-X** clears both marks without changing cues or selection. Space controls playback when a toolbar button has focus; typing spaces in text fields still works. Unknown cues use yellow; identified references have distinct colors and repeated uses share their reference color.

A playhead in a gap or exactly on the boundary makes no trim. These edits preserve all other cue positions and support Undo/Redo. They change cue boundaries without removing time from the source program or shifting later cues.

### Select and navigate

Click a cue to select it. Command/Ctrl-click toggles additional cues; Shift-click selects a range.

In the timeline, **Down** seeks to the next edit and **Up** to the previous edit (cue starts and ends, including gaps). The same Up/Down edit navigation works with the cue sheet focused; Shift+Up/Down extends row selection.

### Drag and roll boundaries

Drag an edge to trim. At a shared join, hover just inside the left cue to trim its out point, just inside the right cue to trim its in point, or directly on the join to roll both sides together. The hover highlight shows the target.

Boundaries normally follow the project frame grid; release saves one edit. **Escape** or **Command/Ctrl-Z** during a drag cancels it.

### Snap to the playhead

**Program → Snap edits to playhead** turns magnetic cursor snapping on or off. It is on by default and remembered across sessions.

Locate the exact cue start/end with the playhead, then drag an edge or shared join near that line: it locks to the exact playhead time, which takes priority over the normal frame grid. The playhead highlights green while snapped.

Pull farther away to release the snap. The capture distance stays consistent on screen as you zoom, and snapping never permits an invalid cue duration.

### Draw a cue

**Shift-drag** in either direction draws a new cue. Double-click it to name it or assign a reference. Trims and removals leave empty space; existing cues are not replaced by drawing an overlap.

Click and drag from empty timeline space (including below the cues on the waveform) to lasso cues touched by the selection box. Command/Ctrl-drag adds to the selection; Escape restores the previous selection. A click without dragging still places the free-play cursor.

### Merge cues

**M** merges selected adjoining cues with a reference-confirmation dialog. Right-click a cue, or use the cue action menus, for Review, Merge, Exclude/Restore, Add, or Delete.

### Delete cues

**Delete / Backspace** deletes the selected cue or cues in the cue sheet or timeline, after a confirmation (No is the default). This also works in the Excluded view. A held key does not repeatedly ask. Deletion leaves empty space and can be undone with **Edit > Undo**. Text fields keep their normal text deletion. **More** and the waveform right-click menu also offer **Delete selected cues**.

### Exclude and restore

**Exclude** hides a cue from the working sheet and exports while preserving it. Select **Excluded** in the table filter, or enable **Excluded cues** in expanded waveform view, then use **Restore** to bring it back.

### Undo and redo

**Edit > Undo / Redo** uses Command/Ctrl-Z and Command/Ctrl-Shift-Z. The last 50 cue edits persist across reopening. New analysis, source replacement, reference removal, or coverage repair resets cue history. Text fields retain native text undo.

## Retry identification and compare references
To identify a new cue:

1. Hold **Shift** and drag over the music interval to draw a cue, or use **Add cue…**.
2. Select that cue and choose **Identify selected cue** from its right-click menu or the **Cues / More** menu.
3. Select a result and choose **Review candidate**. The review opens with the matched reference and its title filled in automatically.
4. Compare playback, adjust the title if needed, set the review status, and choose **Save**. Accepting a candidate alone does not save it. Cancel leaves the original cue unchanged.

### Search an interval

Select one cue, including a newly drawn or trimmed Unknown, then choose **Identify selected cue** in the waveform right-click menu, expanded waveform **Cues** menu, or cue-sheet **More** menu. Only that interval is searched. Results show candidate references and landmark support; support is evidence, not a probability. Review a candidate before saving.

Retry never changes neighboring cues or fills gaps. Cancel or no match leaves the cue sheet unchanged. Stored reference fingerprints work even when original reference files are offline.

### Compare the match

In **Review cue**, select a reference and switch between **Program cue** and **Reference** playback. Only one plays at a time. **Reference in** chooses the reference position; new full analyses and accepted retries provide an estimated matching position. Older projects may require manual positioning or another Identify pass. Mark **Review status → Reviewed** when you confirm the assignment, then Save.

### Set reference volume

Reference playback defaults to **−12 dB relative to program playback**. **Project → Project settings → Reference playback level** changes the project default. In Review, adjust **Reference level** for that track, or check **Project default** to clear the override. Levels apply only to playback and are saved when the review is saved; they do not change source files, fingerprinting, cue timing, or exports.

### Reconnect missing recordings

Reference playback is disabled for missing/changed media. **Reconnect** in review, **Reference library → Relink**, or **Library → Reconnect selected reference** verifies the original recording and reconnects it without rebuilding fingerprints. Identification and export remain available without linked originals. Fingerprints cannot recreate playable audio.

### Audio separation

AI dialogue/music separation is not currently enabled. It would require an optional model download, a separate compatible runtime, local processing time and temporary storage, plus a pilot to verify recognition improves. Vocal separation can also remove singing and damage musical landmarks. No AI models are installed automatically.

## Transitions
Click an edge, then **Audition** (or **A** with the waveform focused) to listen across it. **Loop** repeats that window. **⋯** offers explicit In/Out audition, seconds before and after the boundary, and frame nudges. **Comma / period** nudges the selected edge by one frame. A selected shared join nudges both sides.

Matching settings apply on the next analysis. Timecode changes affect display and exports immediately. Manual cue dialog times are elapsed program seconds; out points are exclusive. Evidence scores are not probabilities. Identified merges become Reviewed after confirming the reference for the entire merged interval, including any gaps.

## Detection sensitivity and silence
Open **Project → Project settings → Detection sensitivity**. **Conservative** is the default: it requires stronger evidence and longer supported music segments to reduce false matches. **Balanced** uses the previous default matching thresholds. **Sensitive** looks for shorter/fainter cues but can produce more false candidates. **Custom** preserves manual threshold changes. Presets affect both full analysis and **Identify selected cue**; changing them does not rewrite your current cue sheet. Reanalyze to apply them to the full program, or retry an individual cue.

The **Silence gate (dBFS)** controls audio-activity filtering. The new default is −65 dBFS; lowering it (for example to −75) keeps quieter audio, while raising it treats more background noise as silence. New analysis leaves silent stretches empty and splits automatically detected cues across substantial silence. Very short pauses remain inside a cue and small boundary padding protects fades. Unmatched fragments under 0.25 seconds are omitted to avoid tiny edge artifacts. Audible dialogue and effects may still be Unknown; activity detection is not a music classifier. Repair preserves existing reviewed/manual/excluded rows and adds only audible unmatched intervals. It does not silently delete existing decisions.

## Sources, references, and export

**Library → Metadata → Recover embedded metadata…** previews missing fields that can be recovered from stored tags, including named iXML library/album attributes, PRO affiliations and structured rights parties. It works with offline reference media, preserves existing values, and creates a recovery snapshot before applying changes.

In **Reference library → Metadata → Edit selected reference**, use **Rights parties** to edit each writer/publisher's role, name, PRO, IPI (including leading zeros), and share percentage. Writer and publisher shares are separate; a blank share means unknown. Composer and publisher text edits synchronize with structured parties. PRO is a summary of the individual affiliations; edit those in Rights parties. Additional fields store provider, provider track ID, source URL, version, album title, catalog code and track number. **Metadata sources** shows change history; imported information remains unverified.

**Reference library → Metadata → Import metadata JSON…** accepts an edited reference-library export. Choose **Apply edits** to correct existing values, or **Fill blank fields only** to preserve existing values. Preview old and new values before applying. Unmatched or stale conflicting entries are reported and skipped. See **JSON licensing round-trip** for the full format and examples. The APM search button opens a catalog search for manual lookup; automatic online retrieval is not configured.

Use **Reference library → Metadata → Export metadata JSON…** (or **Library → Metadata → Export metadata JSON…**) to save metadata for every reference, including tracks unused in the program. The JSON includes all supported cue-sheet metadata fields, blank values for missing information, original embedded tags, reference IDs, file paths, durations, and an original-values baseline for detecting stale edits. It exports the metadata currently stored in the project; it does not look up missing credits online.
Analysis creates Unknown rows for audible unrecognized intervals; silent stretches stay empty. Manual editing can intentionally leave gaps. **Cue sheet > Repair full-source coverage** rereads the source and fills audible unmatched gaps with Unknown while preserving existing cues; silent gaps stay empty.

Coverage reports the union of cue intervals; Identified reports time assigned to references. Overlaps may make summed cue durations exceed program duration. Excluded rows are omitted from CSV/Excel exports. Reference metadata remains attached to the original reference. Imported licensing tags are not proof of clearance.

All analysis runs locally. Changes save automatically. If a source file changes, analyze that cut again; if it moves, relink it through Program. Missing audio streams and incomplete audio decoding report an error without replacing the existing cue sheet.

## Review queue
Open **Review queue** in the main header or **Cue sheet → Review queue**. The count shows how many included cues still need attention.

### What remains in the queue

Unknown cues and unreviewed reference assignments appear in time order. Unreviewed assignments below the evidence threshold also show **Weak match**. The threshold defaults to 60 and can be adjusted in the queue; an evidence score is not a probability. A manually **Reviewed** assignment is confirmed even when its original evidence score is low. Excluded cues stay out of the queue.

### Work through the queue

Use **Previous / Next** or **Go to cue** to select the interval and move the playhead there.

**Review…** opens its assignment and **Identify…** searches the selected interval. The queue updates after saved changes.

**R** jumps to the next outstanding cue from the waveform or cue sheet and wraps to the first remaining item at the end.

## Recovery snapshots
Open **Project → Recovery snapshots** to see dated recovery points, their reasons, and sizes. **Snapshot now** saves an additional recovery point. **Restore selected…** restores the complete project state, including cues, reference fingerprints, metadata, settings, and markers. A new snapshot preserves the current state before restoring.

Restoring replaces the whole project database. Choose a recovery point based on its timestamp and reason, then check the restored cues before continuing.

### When recovery points are saved

Full snapshots are forced before analysis replacement, source-coverage repair, program replacement, and reference removal or reindexing. Routine cue edits—including deletions, merges, trims, and exclusions—save immediately with durable Undo/Redo and never copy the full fingerprint library. Metadata edits, reference additions, and marker edits create a full recovery point when the previous one is at least five minutes old. Full checkpoints can take time for very large projects. If a required snapshot cannot be saved, the edit is stopped and an error is shown.

### Retention and linked media

The newest 20 snapshots are kept in the hidden **.cueatlas-snapshots** folder beside the project, grouped by a stable project identity. Renaming a project in the same folder keeps its recovery history. Keep that folder with the project when moving it if you need those recovery points.

Snapshots contain database data and links to recordings, not copies of the recordings. Separate backups are still useful for long-term storage.

## Validate before export
Use **Cue sheet → Validate cue sheet** at any time. Export opens the save dialog directly. Choose **Show warnings…** there to inspect the report; warnings do not require acknowledgment. Invalid cue timings open validation instead and must be corrected. Handoff packages still offer a validation review.

### Read the report

The report flags missing composer or publisher metadata, Unknown cues, unreviewed assignments, overlaps, and invalid timing. Excluded cues are omitted. Overlaps may be intentional transitions; inspect them rather than assuming they are wrong.

### Resolve or acknowledge issues

**Go to selected cue** returns to the interval that needs attention. Invalid timing must be fixed before export. Other warnings are optional to review through **Show warnings…** in the export save dialog. Validation reports gaps in the supplied information; it does not verify licensing or rights clearance.

## Markers and comments
Place the playhead at a moment that needs attention and press **B**, or choose **Cue sheet → Add marker at playhead**. Enter a comment and adjust the elapsed program position if needed. Blue dotted lines and labels mark these comments on the timeline; hovering near a marker shows the full comment.

### Manage saved comments

Open **Cue sheet → Markers and comments** to add, edit, delete, or jump to a marker. Comments save in the project and are included in handoff packages as **markers.json**.

Markers are independent of cue intervals: trimming or deleting a cue does not remove its nearby comments. Marker changes use recovery snapshots rather than cue Undo/Redo.

### Comments and temporary marks

I/O marks used to create cues are temporary; marker comments are saved. When changing to a different program cut, review existing markers to check that their times still apply.

## Reference duplicates and alternate mixes
Exact duplicate files are skipped during reference import using their SHA-256 file checksums, including duplicates within the same import. Existing legacy references are checked when matching-size files are available. Files with different embedded tags can have different checksums even when the audio sounds identical.

### Inspect flagged pairs

Open **Library → Reference duplicates and alternate mixes** to inspect existing flagged pairs. The reference library also shows flags in its Media column.

**Exact duplicate** means the file checksums match. **Possible alternate mix** means the base titles match after removing common mix labels; it is a title-based suggestion, not verified audio similarity. Listen and inspect metadata before deciding whether to keep or remove a reference. Missing media can still be compared when a checksum was stored previously.

## Project handoff
Choose **Project → Create handoff package**, review the validation report, and select a new output folder. Choose reports only, program media, or program plus all reference media. Packaging runs in the background and can be cancelled.

### Inside the package

The folder contains a project copy, **cue-sheet.csv**, **validation.json**, **markers.json**, **manifest.json**, and a short README. Included recordings go into a **media** subfolder and use relative links so the package can be moved. The original project is preserved. Existing destination folders are never replaced.

### Missing or external media

Requested media that is missing is listed in the manifest and completion message. Media you did not include keeps its original external link. 

Send the entire folder to a recipient using Cue Atlas 0.5 or newer, and keep **media** beside the project. Recovery snapshot history stays with the source project; the handoff begins a separate recovery history. A project-and-reports package can still identify against stored fingerprints while recordings are offline, but playback requires available media.
## Credit lists and rights parties

Credit lists split at commas, semicolons, new lines, and spaced slash separators outside parentheses or brackets. Slashes within names such as **Sony/ATV Songs LLC**, and affiliations such as **(SACEM/BIEM)**, stay intact. Combined affiliations are stored together in the party’s PRO field. Put names containing commas in double quotes when pasting a list, for example **"Smith, John" (PRS)**.

To repair a previously split list, open **Metadata → Edit selected reference → Rights parties → Paste credit lists…**. Paste the original composers and publishers into their separate fields, choose **Preview parties**, review the names and affiliations, then **Use these parties**. This replaces the editor’s party rows, including their IPI/share values. The reference updates only after you **Save** metadata; Cancel leaves the stored reference unchanged. Existing saved parties are never automatically reparsed.

## JSON licensing round-trip
Export reference metadata, edit it in an external app, then preview and import your corrections. Linked cues and subsequent cue-sheet exports use the updated reference metadata automatically. You do not need to analyze or fingerprint the recordings again.

### Export, edit, import
1. Open the **Reference library** tab. Choose **Metadata → Export metadata JSON…** from its single-row toolbar.
2. Save the JSON file and edit values inside each track's **metadata** object. Keep its **reference_id** and **original_metadata** unchanged.
3. From the same **Metadata** menu, choose **Import metadata JSON…** and select the edited file. The same menu is also available at **Library → Metadata** in the menu bar.
4. Choose **Apply edits to existing references**, then **Preview changes**. Check the Before / After values and any skipped-entry messages.
5. Choose **Apply changes** to save all previewed updates together. Cancel leaves the project unchanged. A recovery snapshot is created before applying.

The export contains the full reference library, including references not currently used in cues. You may remove tracks you do not want to update from the JSON's **tracks** array.

### Minimal JSON example
This is a valid patch document. Replace the sample reference ID with the exact ID from your own export. You can supply one track or many.

```json
{
  "format": "cueatlas.reference-metadata",
  "schema_version": 1,
  "tracks": [
    {
      "reference_id": "PASTE_ID_FROM_EXPORT",
      "metadata": {
        "license": "License 2026-001",
        "composer": "Alex Example (BMI)",
        "publisher": "Example Publishing (BMI)",
        "copyright": "2026 Example Music",
        "isrc": "USABC2600001",
        "notes": "Approved for this production"
      }
    }
  ]
}
```

Use standard UTF-8 JSON: double-quoted names and text, no comments, no trailing commas, and no duplicate keys. Identifiers such as ISRC, IPI, catalog numbers, and provider track IDs must be strings so leading zeros are retained.

### Replace, preserve, or clear
- In **Apply edits** mode, a changed supplied field replaces its current value.
- An omitted metadata field stays as it is.
- An empty string such as **"license": ""** clears that text field. Blank values are visible in the preview.
- Text fields cannot be **null**. Use an empty string to clear them.
- **Fill blank fields only** preserves existing values and does not clear fields. Conflicting entries are reported instead of overwritten.

New exports include **original_metadata** beside **metadata** for each track. Do not edit that baseline: unchanged exported values are ignored, and conflicts with newer project edits are reported. Export again to reconcile a stale entry. A minimal patch without a baseline applies its supplied values directly after preview; it cannot detect edits made since a previous export.

### Writers, publishers, affiliations, and shares
For detailed rights credits, edit **metadata.parties**. Keep each affiliation, IPI, and share attached to its writer or publisher. Here is an example parties value:

```json
[
  {
    "role": "composer",
    "name": "Alex Example",
    "pro": "BMI",
    "ipi": "00012345678",
    "share_percent": 100
  },
  {
    "role": "publisher",
    "name": "Example Publishing",
    "pro": "BMI",
    "ipi": "00098765432",
    "share_percent": null
  }
]
```

Allowed roles are **composer**, **author**, **composer_author**, **arranger**, **publisher**, and **subpublisher**. A share is a number from 0 to 100, or **null** when unknown. Writer and publisher shares are separate; the app does not infer missing shares or confirm ownership.

Editing the parties list regenerates the composer, publisher, and aggregate PRO text summaries. Leave those summaries unchanged in a round-trip export, or omit them from a patch. If you edit both parties and their summaries, the edited values must agree. An empty parties array explicitly clears all structured credits and their summaries.

For simple text-credit edits, the importer updates the corresponding parties while preserving an existing IPI and unsupplied affiliation/share for a uniquely matching name. To remove or correct a specific party's PRO, IPI, or share, edit that party directly. Conflicting structured and text edits are reported for reconciliation.

### Matching existing references
The exact **reference_id** from the export is the preferred match. If a supplied ID no longer exists, the entry is skipped rather than redirected to another reference.

When no ID is supplied, a unique **provider** plus **provider_track_id** can match. An exact absolute **reference_file** path can also match when no provider match is found. Titles and filenames alone are never used to select a recording, and the import never creates new references or changes cue timings.

### Supported editable fields
Text fields: **title**, **artist**, **composer**, **publisher**, **pro**, **isrc**, **iswc**, **copyright**, **license**, **library**, **catalog**, **notes**, **provider**, **provider_track_id**, **source_url**, **version**, **album_title**, **catalog_code**, and **track_number**. Structured credits use **parties** as described above.

Leave the export's format, schema version, reference IDs, file paths, durations, original metadata baseline, raw embedded tags, and metadata-source history intact. Imports update supported metadata fields only. Original tags, fingerprints, source audio files, cue timings, assignments, cue notes, and review status are preserved. Changes are recorded in the reference's metadata-source history; imported licensing information still needs human verification.
'''.replace('{version}', __version__)


GUIDE += '''
## Split a cue

Select one cue, place the playhead inside it, and press **S**. You can also choose **Split cue at playhead** from the cue menus or the waveform right-click menu. Both pieces keep the original reference, licensing link, review state, notes, and exclusion state. Splitting leaves neighboring cues unchanged. Edit → Undo restores the original cue; Redo repeats the split. The split point must be inside the cue, away from either boundary. S can be reassigned in Edit → Keyboard shortcuts.

## Standard + AI follow-up

Click **Analyze** (or **Program → Analyze program**) and choose **Standard + AI follow-up**. The original program mix is searched first. Only remaining Unknown intervals receive AI separation, with four seconds of surrounding context where available; matching and playback use the exact original cue interval. Long initial Unknowns are divided into sections of at most two minutes for follow-up. Known music is not sent through AI again. Song/version questions already found in the standard pass go straight to review instead of consuming AI processing.

The standard pass saves its results before follow-up starts. Canceling the standard pass preserves the previous analysis. Canceling or encountering an error during AI follow-up keeps the completed standard pass and any completed follow-up proposals. Reanalyzing still requires the normal replacement confirmation and creates a recovery snapshot.

Review original and AI evidence side by side. Original-mix evidence takes priority when it distinguishes a recording version. A neighboring music cue can support a candidate when the exact recording and its reference playback position agree; a neighbor's title alone cannot create a match. Apply the checked proposals with **Apply matches & merge**. A join requires touching intervals, the same reference ID, consistent reference positions, and evidence covering the proposed interval. Partial matches remain separate and need boundary review. Gaps, excluded cues, different versions, and inconsistent reference positions are not joined automatically. One Undo reverses the application, joins, and associated version-review information.

## Vocal, instrumental, and alternate versions

Related titles such as Song and Song Instrumental suggest a possible song family. Meaningful title differences and conflicting library/provider/artist/composer information prevent some unrelated songs from being grouped. These are hints, not proof of an audio match; all reference IDs, source paths, rights parties, and licensing metadata remain separate.

Strong original-mix evidence that distinguishes one version is retained even when the AI-separated music favors an instrumental. If versions have conflicting original evidence, or AI-only evidence cannot distinguish versions, the default result is **Version needs review** rather than a guessed recording. Applying this default records the proposed song as an unassigned **Needs review** cue, with no recording-specific license attached.

Use **Use reference / version** and **Review candidate** to listen to the alternatives. Main cue review places the proposed versions first in the Reference list and uses each supported recording's own reference position. Entries labeled **Compare version** are title-related alternatives without a supporting audio match; they start at zero and require listening confirmation. Missing references can be reconnected, and reference playback retains the project's default −12 dB level and per-track overrides. Fingerprints cannot reconstruct a reference recording.

Select the exact recording and Save to assign its own metadata. Until then, the cue title and review queue show Version needs review. Splitting preserves those version choices, and Undo/Redo restores version-review state along with the cue edit.

## First-pass AI program analysis

Click **Analyze**, or open **Program → Analyze program**, then choose **Full-program AI separation**. **Standard analysis** remains the faster option. If the optional engine is missing, its installation window opens first.

AI analysis separates music across the entire program before searching the reference library, including MP4/MOV audio. Processing uses bounded sections with overlapping context. Cue timing, waveform display, playback, and exports continue to use the original program and its full duration. Normal project sensitivity settings still apply, and matching is possible from stored fingerprints even when reference source files are offline. Automatic matches remain Needs review.

This mode takes longer than standard analysis. Progress and Cancel remain available; cancellation or separation failure preserves the previous cues. Completed separated sections are cached and can be reused on a later attempt. Clear cached audio in AI setup removes these derived sections. Full-program analysis needs additional temporary/cache space, checked before separation. Reanalyzing replaces existing cues only after the usual confirmation and successful processing; a recovery snapshot is saved first.

## Optional AI music separation

For timeline listening, **Option/Alt-drag** to mark a range, or set **I/O** marks or select cues, then click **Separate range** above the waveform. Marks take priority over selected cues. This processes audio only: cues, licensing, and Undo history stay unchanged. Click **Program audio / AI music** to compare at the same cursor position. The waveform changes with the audio. Blue strips show where AI audio is available. Outside those sections the original audio plays, labeled **outside AI sections**. The switch can reuse cached full-program or cue-retry AI audio without another inference pass. New ranges require the optional add-on; listening to cached audio does not. Escape clears the marks; Shift-drag still creates a cue.

Open **Project → Project settings → AI music separation** and click **Install**. Settings is available before opening a project, so the add-on can be installed independently. Download stages show megabytes and a percentage; library setup and verification show an animated activity bar with the current operation. This optional local add-on supports Apple Silicon Macs. Installation downloads a 447 MB BandIt model plus Python and supporting libraries, about 1.6 GB installed. Allow at least 3 GB free for setup. Installation needs internet access; processing afterward is local. The main app and normal matching work without this add-on.

For one or more selected cues, choose **Reduce dialogue and retry** from a cue menu or right-click menu. To search every included Unknown cue, use **Cue sheet → Analyze all Unknown cues with separation**. Excluded cues are skipped. Split intervals longer than five minutes before processing. The add-on reduces dialogue and effects, then searches the existing reference fingerprints using the project's current sensitivity settings. It also searches the original audio for comparison. A reference recording does not need to be connected for fingerprint matching.

Results show original and AI candidates. Listen with **Play original** and **Play music**, or open **Review candidate** to compare with the original reference when it is linked. Reference comparison uses the configured playback level (default −12 dB). Matches are proposals, not confirmed identifications. Check the matches to use, then **Apply matches & merge**. Applied matches are marked **Needs review**. Touching cues with the same reference are joined, including existing known neighbors; gaps, excluded cues, and different references remain separate. One **Undo** reverses the batch application and joins.

Cancel stops processing and retains completed results. **Cue sheet → Review last AI results** reopens them. Cue changes, changed media, settings, or library changes may require a fresh search before applying. Separated audio is cached for reuse. **Clear cached audio** removes these derived recordings; **Uninstall** removes only the optional model and runtime. Neither removes source recordings, references, or cue sheets. Cached audio remains until cleared.

'''
