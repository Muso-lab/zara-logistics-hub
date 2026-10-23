Attribute VB_Name = "Modulo7"
Sub test()
Attribute test.VB_ProcData.VB_Invoke_Func = " \n14"
'
' test Macro
'

'
    Sheets("Planning Roma").Select
    ActiveWindow.SmallScroll Down:=-21
    Range("F37:S60").Select
    Selection.Copy
    Application.CutCopyMode = False
    Sheets("PROCEDURE").Select
    ActiveWindow.SmallScroll Down:=-9
    Range("G28").Select
End Sub
