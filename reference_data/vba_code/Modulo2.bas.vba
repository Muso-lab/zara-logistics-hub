Attribute VB_Name = "Modulo2"
Sub STAMPA()
Attribute STAMPA.VB_ProcData.VB_Invoke_Func = " \n14"
'
' STAMPA Macro
'

'
'    Sheets("SPUNTA ARRIVI ").Select
'    Range("A1:S110").Select

'
' COPIA_SU_FOGLIO Macro
'

'
    Cells.Select
    Sheets("SPUNTA ARRIVI ").Select
    Sheets("SPUNTA ARRIVI ").Copy
    Selection.Copy
    Selection.PasteSpecial Paste:=xlPasteValues, Operation:=xlNone, SkipBlanks _
        :=False, Transpose:=False
    Application.CutCopyMode = False
    ActiveWorkbook.SaveAs Filename:="\\10.0.0.3\dati\scambio\ZARA - NON TOCCARE\Analisi_ZARA\OUTPUT\ZARA.xlsx", _
        FileFormat:=xlOpenXMLWorkbook, CreateBackup:=False
    Range("A1").Select
   ' ActiveWindow.Close
    
    Windows("ZARA.xlsx").Activate
    Workbooks.Open Filename:= _
        "\\10.0.0.3\dati\scambio\ZARA - NON TOCCARE\Analisi_ZARA\OUTPUT\ZARA.xlsx"
    Cells.Select
    Selection.Copy
    Selection.PasteSpecial Paste:=xlPasteValues, Operation:=xlNone, SkipBlanks _
        :=False, Transpose:=False
    Application.CutCopyMode = False
    ActiveWorkbook.Save
    ActiveWindow.Close
    
    Call esporta_0
    
    Call esporta_9
    
  MsgBox "FILE ESPORTATI"

End Sub

