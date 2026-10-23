Attribute VB_Name = "Modulo3"
Sub esporta_0()
Attribute esporta_0.VB_ProcData.VB_Invoke_Func = " \n14"
'
Call CompilaAndataRitornoFlussiEsatto
'

'
    ActiveWindow.TabRatio = 0.937
    Sheets("SGA_DEF_0").Select
    Sheets("SGA_DEF_0").Copy
    ChDir "\\10.0.0.3\dati\scambio\ZARA - NON TOCCARE\Analisi_ZARA"
    ActiveWorkbook.SaveAs Filename:="\\10.0.0.3\dati\scambio\ZARA - NON TOCCARE\Analisi_ZARA\OUTPUT\barrazero_Sga.xlsx", _
        FileFormat:=xlOpenXMLWorkbook, CreateBackup:=False
    ActiveWindow.Close
        ActiveWindow.TabRatio = 0.355
            Sheets("PROCEDURE").Select
End Sub


Sub esporta_9()
'
' esporta_0 Macro
'
Call CompilaAndataRitornoFlussiVariante9
'
    ActiveWindow.TabRatio = 0.937
    Sheets("SGA_DEF_9").Select
    Sheets("SGA_DEF_9").Copy
    ChDir "\\10.0.0.3\dati\scambio\ZARA - NON TOCCARE\Analisi_ZARA"
    ActiveWorkbook.SaveAs Filename:="\\10.0.0.3\dati\scambio\ZARA - NON TOCCARE\Analisi_ZARA\OUTPUT\barranove_Sga.xlsx", _
        FileFormat:=xlOpenXMLWorkbook, CreateBackup:=False
    ActiveWindow.Close
        ActiveWindow.TabRatio = 0.355
            Sheets("PROCEDURE").Select
End Sub

