# Reference metadata recovery and enrichment

Start with **Project → Recover embedded reference metadata…**. Review the proposed values and click **Apply changes**. This reads tags already stored in the project, including complete iXML, and works when the original audio is offline. It fills blank fields and records the fields changed. Existing titles, edited credits, raw tags, fingerprints, cue timing, and assignments are preserved. A recovery snapshot is made before the batch is saved.

Use **Reference library → Edit metadata → Rights parties** for individual corrections. Each party has a role, name, PRO affiliation, IPI string and optional share percentage. Preserve leading zeros in IPI numbers. Blank shares remain unknown; do not infer equal shares or combine writer and publisher totals. The existing composer, publisher and PRO text fields summarize the parties when saved. The Metadata sources tab records changes, not rights verification.

Additional text fields distinguish provider, provider track ID, source URL, version, album title, catalog code and track number. The legacy Catalog field remains for compatibility. Provider IDs are separate from CueAtlas's internal reference IDs. Album title does not become a catalog code unless a recognized code is explicitly present in a tag.

## External credits

For APM, **Find on APM…** in the metadata dialog opens a search using the provider track ID, or the title if no ID is available. Confirm the exact version before entering credits. CueAtlas does not currently retrieve credits automatically from APM or assume that a library/artist name is a composer or publisher.

For batch enrichment, export the reference library JSON and supply additional metadata in a copy, then choose **Project → Import reference metadata JSON…**. The outer object contains a `tracks` list, as in this minimal example:

```json
{
  "tracks": [
    {
      "reference_id": "COPY_THE_REFERENCE_ID_FROM_YOUR_EXPORT",
      "metadata": {
        "provider": "APM Music",
        "provider_track_id": "PROVIDER_TRACK_ID",
        "source_url": "https://www.apmmusic.com/search",
        "parties": [
          {
            "role": "composer",
            "name": "Example Writer",
            "pro": "BMI",
            "ipi": "00012345678",
            "share_percent": 100
          },
          {
            "role": "publisher",
            "name": "Example Publisher",
            "pro": "BMI",
            "ipi": "00087654321",
            "share_percent": 100
          }
        ]
      }
    }
  ]
}
```

Values in this example are placeholders. Use `null` for an unknown share. Supported roles are `composer`, `author`, `composer_author`, `arranger`, `publisher`, and `subpublisher`.

Entries match by internal `reference_id`. When it is omitted, a unique existing provider/track ID pair can be used. Titles and filenames are not matching keys. An unknown supplied reference ID is skipped rather than falling back to a different recording.

Review the full preview before applying. The importer fills blanks, and can fill an existing party's missing IPI, PRO or share when role and name match. It skips conflicting entries; replacing established values or adding parties to an existing party list requires explicit editing. Unknown JSON properties are not executed or applied. Original audio and embedded tags are never rewritten. Imported data is recorded as unverified, with the import filename, source URL where supplied, timestamp and changed fields.

JSON exports preserve structured parties and history. CSV/Excel cue sheets also include provider/version/album fields and JSON columns for Rights Parties and Metadata Sources. Existing text credit columns remain available.
