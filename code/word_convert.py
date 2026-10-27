#!/usr/bin/env python3
"""Open the IEEE .doc template via Word COM, save a .docx copy, and dump its styles."""
import os
import sys
import win32com.client as win32

tpl = os.path.abspath(sys.argv[1])
out = os.path.abspath(sys.argv[2])

word = win32.Dispatch("Word.Application")
word.Visible = False
word.DisplayAlerts = 0
try:
    doc = word.Documents.Open(tpl)
    doc.SaveAs2(out, FileFormat=16)  # 16 = wdFormatXMLDocument (.docx)
    names = []
    for s in doc.Styles:
        try:
            if s.InUse:
                names.append(s.NameLocal)
        except Exception:
            pass
    print("SAVED:", out)
    print("IN-USE STYLES:", " | ".join(sorted(set(names))))
    doc.Close(False)
finally:
    word.Quit()
