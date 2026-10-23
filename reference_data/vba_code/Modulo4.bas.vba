Attribute VB_Name = "Modulo4"
Sub COPIA_SU_FOGLIO()
Attribute COPIA_SU_FOGLIO.VB_ProcData.VB_Invoke_Func = " \n14"
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
    ActiveWorkbook.SaveAs Filename:="C:\Users\lucia\OneDrive\Desktop\ZARA.xlsx", _
        FileFormat:=xlOpenXMLWorkbook, CreateBackup:=False
    Range("A1").Select
    ActiveWindow.Close
End Sub
