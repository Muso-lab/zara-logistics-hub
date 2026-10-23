Attribute VB_Name = "Modulo6"
Sub EXPORT_PLANNER()
Attribute EXPORT_PLANNER.VB_ProcData.VB_Invoke_Func = " \n14"
'
' EXPORT_PLANNER Macro
'

'
    ChDir "\\10.0.0.3\dati\scambio\ZARA - NON TOCCARE\Analisi_ZARA"
    Workbooks.Open Filename:= _
        "\\10.0.0.3\dati\scambio\ZARA - NON TOCCARE\Analisi_ZARA\Planning ITX_RM.xlsx"
    Windows("Planning ZARA.xlsm").Activate
    Sheets("Planning Roma").Select
    ActiveWindow.SmallScroll Down:=-51
    Range("F7:S73").Select
    Selection.Copy
    Windows("Planning ITX_RM.xlsx").Activate
    Range("F7").Select
    Selection.PasteSpecial Paste:=xlPasteValues, Operation:=xlNone, SkipBlanks _
        :=False, Transpose:=False
    Windows("Planning ZARA.xlsm").Activate
    Range("V7:V73").Select
    Range("V73").Activate
    Application.CutCopyMode = False
    Selection.Copy
    Windows("Planning ITX_RM.xlsx").Activate
    Range("V7").Select
    Selection.PasteSpecial Paste:=xlPasteValues, Operation:=xlNone, SkipBlanks _
        :=False, Transpose:=False
    Application.CutCopyMode = False
    ChDir "\\10.0.0.3\dati\scambio\ZARA - NON TOCCARE\Analisi_ZARA\OUTPUT"
    workbookname = "\\10.0.0.3\dati\scambio\ZARA - NON TOCCARE\Analisi_ZARA\OUTPUT\PLANNER ROMA _"
    datetimesuffix = Format(CStr(Now), "dd-mm-yyyy")
    ActiveWorkbook.SaveAs Filename:=workbookname & datetimesuffix
        ActiveWindow.Close
    Windows("Planning ZARA.xlsm").Activate
    Sheets("PROCEDURE").Select
    Range("G28").Select
   ' Windows("PLANNER ROMA del.xlsm").Activate
    'ActiveWindow.Close+
    MsgBox "FILE ESPORTATO NELLA CARTELLA SCAMBIO\ZARA NON TOCCARE\Analisi_ZARA\OUTPUT\"
End Sub
