Attribute VB_Name = "Modulo1"
Sub PULIZIA()
Attribute PULIZIA.VB_ProcData.VB_Invoke_Func = " \n14"
'
' PULIZIA Macro
'

'
    Sheets("TEXILE").Select
    Rows("1:8").Select
    Selection.Delete Shift:=xlUp
    Sheets("SHOES").Select
    ActiveWindow.SmallScroll Down:=-60
    Rows("1:8").Select
    Selection.Delete Shift:=xlUp
    Sheets("ECOM").Select
    ActiveWindow.SmallScroll Down:=-30
    Rows("1:8").Select
    Selection.Delete Shift:=xlUp
    Range("K18").Select
    
    Call COPIADATI
    
End Sub
Sub COPIADATI()
Attribute COPIADATI.VB_ProcData.VB_Invoke_Func = " \n14"
'
' COPIADATI Macro
'

'
    Sheets("TEXILE1").Select
    Columns("K:P").Select
    ActiveWindow.SmallScroll Down:=-9
    Application.CutCopyMode = False
    Selection.ClearContents
    Sheets("TEXILE").Select
    Columns("A:F").Select
    Selection.Copy
    Sheets("TEXILE1").Select
    Columns("K:K").Select
    ActiveSheet.Paste
    Columns("H:H").Select
    Application.CutCopyMode = False
    Selection.Copy
    Columns("A:A").Select
    Selection.PasteSpecial Paste:=xlPasteAllUsingSourceTheme, Operation:=xlNone _
        , SkipBlanks:=False, Transpose:=False
    Selection.PasteSpecial Paste:=xlPasteValues, Operation:=xlNone, SkipBlanks _
        :=False, Transpose:=False
    Columns("L:P").Select
    Application.CutCopyMode = False
    Selection.Copy
    Columns("B:B").Select
    Selection.PasteSpecial Paste:=xlPasteAllUsingSourceTheme, Operation:=xlNone _
        , SkipBlanks:=False, Transpose:=False
    Selection.PasteSpecial Paste:=xlPasteValues, Operation:=xlNone, SkipBlanks _
        :=False, Transpose:=False
    Columns("A:A").Select
    Application.CutCopyMode = False
    Selection.TextToColumns Destination:=Range("A1"), DataType:=xlDelimited, _
        TextQualifier:=xlDoubleQuote, ConsecutiveDelimiter:=False, Tab:=True, _
        Semicolon:=False, Comma:=False, Space:=False, OTHER:=False, FieldInfo _
        :=Array(1, 1), TrailingMinusNumbers:=True
    Sheets("SHOES1").Select
    Columns("K:P").Select
    Selection.ClearContents
    Sheets("SHOES").Select
    Columns("A:F").Select
    Selection.Copy
    Sheets("SHOES1").Select
    Columns("K:K").Select
    ActiveSheet.Paste
    Columns("H:H").Select
    Application.CutCopyMode = False
    Selection.Copy
    Columns("A:A").Select
    Selection.PasteSpecial Paste:=xlPasteAllUsingSourceTheme, Operation:=xlNone _
        , SkipBlanks:=False, Transpose:=False
    Selection.PasteSpecial Paste:=xlPasteValues, Operation:=xlNone, SkipBlanks _
        :=False, Transpose:=False
    Columns("L:P").Select
    Application.CutCopyMode = False
    Selection.Copy
    Columns("B:B").Select
    Selection.PasteSpecial Paste:=xlPasteAllUsingSourceTheme, Operation:=xlNone _
        , SkipBlanks:=False, Transpose:=False
    Selection.PasteSpecial Paste:=xlPasteValues, Operation:=xlNone, SkipBlanks _
        :=False, Transpose:=False
    Columns("A:A").Select
    Application.CutCopyMode = False
    Selection.TextToColumns Destination:=Range("A1"), DataType:=xlDelimited, _
        TextQualifier:=xlDoubleQuote, ConsecutiveDelimiter:=False, Tab:=True, _
        Semicolon:=False, Comma:=False, Space:=False, OTHER:=False, FieldInfo _
        :=Array(1, 1), TrailingMinusNumbers:=True
    Sheets("ECOM1").Select
    Columns("K:P").Select
    Selection.Copy
    Sheets("ECOM1").Select
    Application.CutCopyMode = False
    Selection.ClearContents
    Sheets("ECOM").Select
    Columns("A:F").Select
    Selection.Copy
    Sheets("ECOM1").Select
    Columns("K:K").Select
    ActiveSheet.Paste
    Columns("H:H").Select
    Application.CutCopyMode = False
    Selection.Copy
    Columns("A:A").Select
    Selection.PasteSpecial Paste:=xlPasteAllUsingSourceTheme, Operation:=xlNone _
        , SkipBlanks:=False, Transpose:=False
    Selection.PasteSpecial Paste:=xlPasteValues, Operation:=xlNone, SkipBlanks _
        :=False, Transpose:=False
    Columns("L:P").Select
    Application.CutCopyMode = False
    Selection.Copy
    Columns("B:B").Select
    ActiveSheet.Paste
    Columns("A:A").Select
    Application.CutCopyMode = False
    Selection.TextToColumns Destination:=Range("A1"), DataType:=xlDelimited, _
        TextQualifier:=xlDoubleQuote, ConsecutiveDelimiter:=False, Tab:=True, _
        Semicolon:=False, Comma:=False, Space:=False, OTHER:=False, FieldInfo _
        :=Array(1, 1), TrailingMinusNumbers:=True
        
        Call OTHER
End Sub
Sub OTHER()
Attribute OTHER.VB_ProcData.VB_Invoke_Func = " \n14"
'
' OTHER Macro
'

'
    ActiveWindow.SmallScroll Down:=-18
    Sheets("OTHER").Select
    ActiveWindow.SmallScroll Down:=-21
    Sheets("OTHER1").Select
    Columns("D:E").Select
    Selection.ClearContents
    Sheets("OTHER").Select
    Application.CutCopyMode = False
    Application.CutCopyMode = False
    ActiveWorkbook.PivotCaches.Create(SourceType:=xlDatabase, SourceData:= _
        "OTHER!R1C1:R44C20", Version:=7).CreatePivotTable TableDestination:= _
        "OTHER1!R1C4", TableName:="Tabella pivot2", DefaultVersion:=7
    Sheets("OTHER1").Select
    Cells(1, 4).Select
    With ActiveSheet.PivotTables("Tabella pivot2")
        .ColumnGrand = True
        .HasAutoFormat = True
        .DisplayErrorString = False
        .DisplayNullString = True
        .EnableDrilldown = True
        .ErrorString = ""
        .MergeLabels = False
        .NullString = ""
        .PageFieldOrder = 2
        .PageFieldWrapCount = 0
        .PreserveFormatting = True
        .RowGrand = True
        .SaveData = True
        .PrintTitles = False
        .RepeatItemsOnEachPrintedPage = True
        .TotalsAnnotation = False
        .CompactRowIndent = 1
        .InGridDropZones = False
        .DisplayFieldCaptions = True
        .DisplayMemberPropertyTooltips = False
        .DisplayContextTooltips = True
        .ShowDrillIndicators = True
        .PrintDrillIndicators = False
        .AllowMultipleFilters = False
        .SortUsingCustomLists = True
        .FieldListSortAscending = False
        .ShowValuesRow = False
        .CalculatedMembersInFilters = False
        .RowAxisLayout xlCompactRow
    End With
    With ActiveSheet.PivotTables("Tabella pivot2").PivotCache
        .RefreshOnFileOpen = False
        .MissingItemsLimit = xlMissingItemsDefault
    End With
    ActiveSheet.PivotTables("Tabella pivot2").RepeatAllLabels xlRepeatLabels
    With ActiveSheet.PivotTables("Tabella pivot2").PivotFields("Tienda")
        .Orientation = xlRowField
        .Position = 1
    End With
    ActiveSheet.PivotTables("Tabella pivot2").AddDataField ActiveSheet.PivotTables( _
        "Tabella pivot2").PivotFields("Enviado3"), "Somma di Enviado3", xlSum
    Columns("D:E").Select
    Selection.Copy
    Columns("M:M").Select
    Selection.PasteSpecial Paste:=xlPasteAllUsingSourceTheme, Operation:=xlNone _
        , SkipBlanks:=False, Transpose:=False
    Selection.PasteSpecial Paste:=xlPasteValues, Operation:=xlNone, SkipBlanks _
        :=False, Transpose:=False
    Columns("P:P").Select
    Application.CutCopyMode = False
    Selection.Copy
    Columns("H:H").Select
    Selection.PasteSpecial Paste:=xlPasteAllUsingSourceTheme, Operation:=xlNone _
        , SkipBlanks:=False, Transpose:=False
    Selection.PasteSpecial Paste:=xlPasteValues, Operation:=xlNone, SkipBlanks _
        :=False, Transpose:=False
    Application.CutCopyMode = False
    Selection.TextToColumns Destination:=Range("H1"), DataType:=xlDelimited, _
        TextQualifier:=xlDoubleQuote, ConsecutiveDelimiter:=False, Tab:=True, _
        Semicolon:=False, Comma:=False, Space:=False, OTHER:=False, FieldInfo _
        :=Array(1, 1), TrailingMinusNumbers:=True
    Columns("N:N").Select
    Selection.Copy
    Columns("I:I").Select
    Selection.PasteSpecial Paste:=xlPasteAllUsingSourceTheme, Operation:=xlNone _
        , SkipBlanks:=False, Transpose:=False
    Selection.PasteSpecial Paste:=xlPasteValues, Operation:=xlNone, SkipBlanks _
        :=False, Transpose:=False
    Range("K14").Select

Call STAMPA

End Sub



Sub IMPORT_OTHER()

    Dim objFSO As Object
    Dim objFolder As Object
    Dim objFile As Object
    Dim myfolder As String
    
    myfolder = "\\10.0.0.3\dati\scambio\ZARA - NON TOCCARE\Analisi_ZARA\OTHER"
    
    Set objFSO = CreateObject("Scripting.FileSystemObject")
    Set objFolder = objFSO.GetFolder(myfolder)

    For Each objFile In objFolder.Files
        Workbooks.Open objFile
        
    Call sistemafile
        
    ActiveWorkbook.Save
        'ActiveWorkbook.Close
    Next objFile
Call PULIZIA
End Sub

Sub sistemafile()

    'Application.ActiveProtectedViewWindow.Edit
    Rows("1:8").Select
    Selection.Delete Shift:=xlUp


'J = 1
i = 1
Cells(1, i).Select
a = Cells(i, 1).Value

Do Until Cells(i, 1).Value = "" And Cells(i + 1, 1).Value = "" And Cells(i + 2, 1).Value = "" And Cells(i + 3, 1).Value = ""
Cells(i, 1).Select
a = Cells(i, 1).Value
If a = "No" Then
i = i + 1

            
Else
ActiveCell.EntireRow.Select
Selection.Delete Shift:=xlUp

End If

Loop

    Range("A1:P1").Select
    Range(Selection, Selection.End(xlDown)).Select
    Selection.Cut
     Application.DisplayAlerts = False

        ActiveWorkbook.Close

        Application.DisplayAlerts = True
    Sheets("OTHER").Select
    'Windows("ZARA.xlsm").Activate
    'Cells(1, 1) = 0
    Range("A2").Select
    b = Cells(2, 1).Value
    If b = "" Then
    ActiveSheet.Paste
    Else
    
    
    'ActiveSheet.Range("a1", ActiveSheet.Range("a1").End(xlDown)).Select
ActiveSheet.Range("a1").End(xlDown).Offset(1, 0).Select
'ActiveSheet.Range("a1:" & ActiveSheet.Range("a1").End(xlDown).Address).Select
'ActiveSheet.Range("a1").End(xlDown).Select
'Cells(1, 1).End(xlDown).Select
'If I > 2 Then
'Range("A1").Select
ActiveSheet.Paste
'Else
'ActiveSheet.Range("A1").End(xlDown).Select
    
 End If
   
    
   'Cells(I + 1, 1).Select

End Sub

Sub SVUOTA_FILE()
'
' SVUOTA_FILE Macro
'

'
    Sheets("SPUNTA PER GIRO").Select
    'Columns("F:F").Select
    'Range("F10").Activate
    'Selection.ClearContents
    'Columns("H:H").Select
    'Range("H10").Activate
    'Selection.ClearContents
    'Columns("J:J").Select
    'Range("J10").Activate
    'Selection.ClearContents
    'Columns("L:L").Select
    'Range("L10").Activate
    'Selection.ClearContents
    'Columns("T:T").Select
    'Range("T10").Activate
    'Selection.ClearContents
    Sheets("TOTALI").Select
    Cells.Select
    Selection.ClearContents
    Sheets("TEXILE").Select
    Cells.Select
    Selection.ClearContents
    Sheets("SHOES").Select
    Cells.Select
    Selection.ClearContents
    Sheets("ECOM").Select
    Cells.Select
    Selection.ClearContents
    Sheets("OTHER").Select
    Range("A2:AA999").Select
    Selection.ClearContents
    Sheets("PROCEDURE").Select
    Range("A1").Select
    
    Call IMPORT_FILE
    
    
End Sub
Sub IMPORT_FILE()
'
' IMPORT_FILE Macro
'

'
    Workbooks.Open Filename:= _
    "\\10.0.0.3\dati\scambio\ZARA - NON TOCCARE\Analisi_ZARA\TOTAL.xls"
    
    ActiveSheet.Range("A1:AA999").Select
    Selection.Copy
    Windows("Planning ZARA.xlsm").Activate
    Sheets("TOTALI").Select
    Selection.PasteSpecial Paste:=xlPasteValues
    Windows("TOTAL.xls").Activate
    Application.DisplayAlerts = False
    ActiveWorkbook.Close
    Application.DisplayAlerts = True
    
    Workbooks.Open Filename:= _
    "\\10.0.0.3\dati\scambio\ZARA - NON TOCCARE\Analisi_ZARA\SHOES.xls"
    
    ActiveSheet.Range("A1:AA999").Select
    Selection.Copy
    Windows("Planning ZARA.xlsm").Activate
    Sheets("SHOES").Select
    Selection.PasteSpecial Paste:=xlPasteValues
    Windows("SHOES.xls").Activate
    Application.DisplayAlerts = False
    ActiveWorkbook.Close
    Application.DisplayAlerts = True
    
    Workbooks.Open Filename:= _
    "\\10.0.0.3\dati\scambio\ZARA - NON TOCCARE\Analisi_ZARA\ECOM.xls"
    
    ActiveSheet.Range("A1:AA999").Select
    Selection.Copy
    Windows("Planning ZARA.xlsm").Activate
    Sheets("ECOM").Select
    Selection.PasteSpecial Paste:=xlPasteValues
    Windows("ECOM.xls").Activate
    Application.DisplayAlerts = False
    ActiveWorkbook.Close
    Application.DisplayAlerts = True
    
    Workbooks.Open Filename:= _
    "\\10.0.0.3\dati\scambio\ZARA - NON TOCCARE\Analisi_ZARA\TEXILE.xls"
    
    ActiveSheet.Range("A1:AA999").Select
    Selection.Copy
    Windows("Planning ZARA.xlsm").Activate
    Sheets("TEXILE").Select
    Selection.PasteSpecial Paste:=xlPasteValues
    Windows("TEXILE.xls").Activate
    Application.DisplayAlerts = False
    ActiveWorkbook.Close
    Application.DisplayAlerts = True
    
    Call IMPORT_OTHER
    
    
End Sub
