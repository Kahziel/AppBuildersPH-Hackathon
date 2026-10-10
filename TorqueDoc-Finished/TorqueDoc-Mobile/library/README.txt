TORQUEDOC BUILT-IN LIBRARY

Every PDF in this folder is part of the application. TorqueDoc indexes
them automatically when it starts. Everything works offline.

HOW TO ADD A MANUAL

1. Put the PDF in the folder of its machine, for example:
     library\cat\C6.4 Engine Service Manual.pdf
   Sub-folders inside a machine folder are fine.
2. Describe it in catalog.json (recommended):
     {
       "file": "cat/C6.4 Engine Service Manual.pdf",
       "title": "C6.4 Engine - Service Manual",
       "variant": "C6.4, serial prefix XXX (as printed on the cover)",
       "revision": "As printed, e.g. RENR1234-05",
       "type": "manual"          (manual, schematic or bulletin)
     }
   A PDF without a catalog entry is still included, but its variant is
   shown as "Not listed in catalog - check the manual cover".
3. Restart TorqueDoc. New, changed and removed PDFs are picked up
   automatically. Large libraries take a while the first time; the
   app shows the progress and stays usable meanwhile.

HOW TO ADD A MACHINE

Add {"id": "...", "name": "..."} to "machines" in catalog.json and create a
folder with the same id. Ids use lowercase letters, digits, - or _.

UPDATES

Newer revisions and service bulletins can also be added in the app with
"Add update". An update can replace a built-in manual; the replaced one
stays viewable but is no longer searched. Updates are stored in data\.

WEB PAGES

List public web pages under "web_sources" in catalog.json:
     {"url": "https://...", "machine": "cat", "title": "...", "variant": "..."}
TorqueDoc saves each one to library\<machine>\web\ as a PDF snapshot when it
is missing and the computer is online (or use Workspace settings > Web
sources > Refresh). The snapshots then work offline. Web pages are not OEM
documentation; results from them are labeled "Web".

IMPORTANT

Only include manuals you are allowed to use and distribute. The training
manual is fictional and must never be used for real maintenance.
