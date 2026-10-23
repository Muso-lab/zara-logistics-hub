Attribute VB_Name = "Modulo8"
Sub CompilaAndataRitornoFlussiEsatto()
    Dim wsFonte As Worksheet
    Dim wsDest As Worksheet
    Dim uRigaFonte As Long
    Dim rigaDest As Long
    Dim i As Long
    Dim testoColli As String
    
    ' Variabili d'appoggio per i dati del negozio letti dalla fonte
    Dim f_Ragg As Variant, f_DataC As Variant, f_DataS As Variant
    Dim f_Mitt As Variant, f_Dest As Variant, f_Peso As Variant
    Dim f_Vol As Variant, f_Coll As Variant, f_RaggVero As Variant

    ' 1. Collegamento dei fogli
    Set wsFonte = Sheets("SGA_FINALE_0")
    Set wsDest = Sheets("SGA_DEF_0")
    
    ' Ci posizioniamo visivamente sulla fonte per sicurezza
    wsFonte.Select
    
    ' 2. Pulizia totale dei vecchi dati su SGA_DEF_0 (mantiene la riga 1 dei titoli)
    Dim uRigaDest As Long
    uRigaDest = wsDest.Cells(wsDest.Rows.Count, "A").End(xlUp).Row
    If uRigaDest >= 2 Then
        wsDest.Rows("2:" & uRigaDest).ClearContents
    End If
    
    ' Trova l'ultima riga della fonte usando la colonna 1 (Raggruppamento)
    uRigaFonte = wsFonte.Cells(wsFonte.Rows.Count, 1).End(xlUp).Row
    
    ' Se non trova righe in quel modo, usa il metodo di riserva UsedRange
    If uRigaFonte <= 1 Then uRigaFonte = wsFonte.UsedRange.Rows.Count
    
    ' La prima riga utile in cui scrivere sul foglio definitivo è la riga 2
    rigaDest = 2
    Application.ScreenUpdating = False
    
    ' 3. Ciclo di lettura riga per riga dal foglio SGA_FINALE_0
    For i = 2 To uRigaFonte
        
        ' Salta la riga in caso di errore nativo di Excel nella colonna 8 (Colli)
        If IsError(wsFonte.Cells(i, 8)) Then GoTo SaltaRiga
        
        testoColli = Trim(CStr(wsFonte.Cells(i, 8).Value))
        
        ' REGOLA: Scrive la coppia Andata e Ritorno solo se i COLLI (colonna 8) sono diversi da zero e validi
        If testoColli <> "" And UCase(testoColli) <> "NAN" And UCase(testoColli) <> "0" And Val(testoColli) > 0 Then
            
            ' CARICAMENTO DATI DALLE COLONNE ESATTE DELLA FONTE (SGA_FINALE_0)
            f_Ragg = wsFonte.Cells(i, 1).Value      ' Colonna 1 = Raggruppamento
            f_DataC = wsFonte.Cells(i, 2).Value     ' Colonna 2 = Data_Carico
            f_DataS = wsFonte.Cells(i, 3).Value     ' Colonna 3 = Data_Scarico
            f_Mitt = wsFonte.Cells(i, 4).Value      ' Colonna 4 = Cod_Mittente
            f_Dest = wsFonte.Cells(i, 5).Value      ' Colonna 5 = Cod_Destinatario
            f_Peso = wsFonte.Cells(i, 6).Value      ' Colonna 6 = Peso
            f_Vol = wsFonte.Cells(i, 7).Value       ' Colonna 7 = Volume
            f_Coll = wsFonte.Cells(i, 8).Value      ' Colonna 8 = Colli
            f_RaggVero = wsFonte.Cells(i, 9).Value  ' Colonna 9 = Ragg_Vero (Sigla giro es. ZA2)
            
            ' =================================================================
            ' 1° RIGA GENERATA: ANDATA (Secondo le tue regole)
            ' =================================================================
            wsDest.Cells(rigaDest, 1).Value = f_RaggVero   ' GIRO = Colonna 9 (Ragg_Vero della fonte)
            wsDest.Cells(rigaDest, 2).Value = f_DataC      ' DATA_CARICO = Colonna 2
            wsDest.Cells(rigaDest, 3).Value = 1            ' COD_MITTENTE = 1
            wsDest.Cells(rigaDest, 4).Value = "MAMONT"     ' MAGAZZINO_CARICO = 'MAMONT'
            wsDest.Cells(rigaDest, 5).Value = f_DataS      ' DATA_SCARICO = Colonna 3
            wsDest.Cells(rigaDest, 6).Value = f_Dest       ' COD_DESTINATARIO = Colonna 5 (Negozio)
            wsDest.Cells(rigaDest, 7).Value = f_RaggVero   ' MAGAZZINO_SCARICO = Colonna 9
            wsDest.Cells(rigaDest, 8).Value = f_Peso       ' PESO = Colonna 6
            wsDest.Cells(rigaDest, 9).Value = f_Vol        ' VOLUME = Colonna 7
            wsDest.Cells(rigaDest, 10).Value = f_Coll      ' COLLI = Colonna 8
            
            rigaDest = rigaDest + 1
            
            ' =================================================================
            ' 2° RIGA GENERATA: RITORNO (Secondo le tue regole)
            ' =================================================================
            wsDest.Cells(rigaDest, 1).Value = f_RaggVero   ' GIRO = Colonna 9 (Ragg_Vero della fonte)
            wsDest.Cells(rigaDest, 2).Value = f_DataC      ' DATA_CARICO = Colonna 2
            wsDest.Cells(rigaDest, 3).Value = f_Dest       ' COD_MITTENTE = Cod_Destinatario andata (Negozio)
            wsDest.Cells(rigaDest, 4).Value = f_RaggVero   ' MAGAZZINO_CARICO = Colonna 9
            wsDest.Cells(rigaDest, 5).Value = f_DataS      ' DATA_SCARICO = Colonna 3
            wsDest.Cells(rigaDest, 6).Value = 1            ' COD_DESTINATARIO = 1
            wsDest.Cells(rigaDest, 7).Value = "MAMONT"     ' MAGAZZINO_SCARICO = 'MAMONT'
            wsDest.Cells(rigaDest, 8).Value = 0            ' PESO = 0
            wsDest.Cells(rigaDest, 9).Value = 0            ' VOLUME = 0
            wsDest.Cells(rigaDest, 10).Value = 0           ' COLLI = 0
            
            rigaDest = rigaDest + 1
            
        End If
        
SaltaRiga:
    Next i
    
    ' Sposta la visualizzazione sul foglio finale per mostrarti il risultato compilato
    wsDest.Select
    
    Application.ScreenUpdating = True
    
   ' MsgBox "Elaborazione completata con successo!" & vbCrLf & _
    '       "Generate " & (rigaDest - 2) & " righe totali nel foglio SGA_DEF_0.", vbInformation, "Fine"
End Sub

Sub CompilaAndataRitornoFlussiVariante9()
    Dim wsFonte As Worksheet
    Dim wsDest As Worksheet
    Dim uRigaFonte As Long
    Dim rigaDest As Long
    Dim i As Long
    Dim testoColli As String
    
    ' Variabili d'appoggio per i dati del negozio letti dalla fonte
    Dim f_Ragg As Variant, f_DataC As Variant, f_DataS As Variant
    Dim f_Mitt As Variant, f_Dest As Variant, f_Peso As Variant
    Dim f_Vol As Variant, f_Coll As Variant, f_RaggVero As Variant

    ' 1. Collegamento dei fogli specifici per la variante 9
    Set wsFonte = Sheets("SGA_FINALE_9")
    Set wsDest = Sheets("SGA_DEF_9")
    
    ' Ci posizioniamo visivamente sulla fonte per sicurezza
    wsFonte.Select
    
    ' 2. Pulizia totale dei vecchi dati su SGA_DEF_9 (mantiene la riga 1 dei titoli)
    Dim uRigaDest As Long
    uRigaDest = wsDest.Cells(wsDest.Rows.Count, "A").End(xlUp).Row
    If uRigaDest >= 2 Then
        wsDest.Rows("2:" & uRigaDest).ClearContents
    End If
    
    ' Trova l'ultima riga della fonte usando la colonna 1 (Raggruppamento)
    uRigaFonte = wsFonte.Cells(wsFonte.Rows.Count, 1).End(xlUp).Row
    
    ' Se non trova righe in quel modo, usa il metodo di riserva UsedRange
    If uRigaFonte <= 1 Then uRigaFonte = wsFonte.UsedRange.Rows.Count
    
    ' La prima riga utile in cui scrivere sul foglio definitivo è la riga 2
    rigaDest = 2
    Application.ScreenUpdating = False
    
    ' 3. Ciclo di lettura riga per riga dal foglio SGA_FINALE_9
    For i = 2 To uRigaFonte
        
        ' Salta la riga in caso di errore nativo di Excel nella colonna 8 (Colli)
        If IsError(wsFonte.Cells(i, 8)) Then GoTo SaltaRiga
        
        testoColli = Trim(CStr(wsFonte.Cells(i, 8).Value))
        
        ' REGOLA: Scrive la coppia Andata e Ritorno solo se i COLLI (colonna 8) sono diversi da zero e validi
        If testoColli <> "" And UCase(testoColli) <> "NAN" And UCase(testoColli) <> "0" And Val(testoColli) > 0 Then
            
            ' CARICAMENTO DATI DALLE COLONNE ESATTE DELLA FONTE (SGA_FINALE_9)
            f_Ragg = wsFonte.Cells(i, 1).Value      ' Colonna 1 = Raggruppamento
            f_DataC = wsFonte.Cells(i, 2).Value     ' Colonna 2 = Data_Carico
            f_DataS = wsFonte.Cells(i, 3).Value     ' Colonna 3 = Data_Scarico
            f_Mitt = wsFonte.Cells(i, 4).Value      ' Colonna 4 = Cod_Mittente
            f_Dest = wsFonte.Cells(i, 5).Value      ' Colonna 5 = Cod_Destinatario
            f_Peso = wsFonte.Cells(i, 6).Value      ' Colonna 6 = Peso
            f_Vol = wsFonte.Cells(i, 7).Value       ' Colonna 7 = Volume
            f_Coll = wsFonte.Cells(i, 8).Value      ' Colonna 8 = Colli
            f_RaggVero = wsFonte.Cells(i, 9).Value  ' Colonna 9 = Ragg_Vero (Sigla giro)
            
            ' =================================================================
            ' 1° RIGA GENERATA: ANDATA
            ' =================================================================
            wsDest.Cells(rigaDest, 1).Value = f_RaggVero   ' GIRO = Colonna 9 (Ragg_Vero della fonte)
            wsDest.Cells(rigaDest, 2).Value = f_DataC      ' DATA_CARICO = Colonna 2
            wsDest.Cells(rigaDest, 3).Value = 1            ' COD_MITTENTE = 1
            wsDest.Cells(rigaDest, 4).Value = "MAMONT"     ' MAGAZZINO_CARICO = 'MAMONT'
            wsDest.Cells(rigaDest, 5).Value = f_DataS      ' DATA_SCARICO = Colonna 3
            wsDest.Cells(rigaDest, 6).Value = f_Dest       ' COD_DESTINATARIO = Colonna 5 (Negozio)
            wsDest.Cells(rigaDest, 7).Value = f_RaggVero   ' MAGAZZINO_SCARICO = Colonna 9
            wsDest.Cells(rigaDest, 8).Value = f_Peso       ' PESO = Colonna 6
            wsDest.Cells(rigaDest, 9).Value = f_Vol        ' VOLUME = Colonna 7
            wsDest.Cells(rigaDest, 10).Value = f_Coll      ' COLLI = Colonna 8
            
            rigaDest = rigaDest + 1
            
            ' =================================================================
            ' 2° RIGA GENERATA: RITORNO
            ' =================================================================
            wsDest.Cells(rigaDest, 1).Value = f_RaggVero   ' GIRO = Colonna 9 (Ragg_Vero della fonte)
            wsDest.Cells(rigaDest, 2).Value = f_DataC      ' DATA_CARICO = Colonna 2
            wsDest.Cells(rigaDest, 3).Value = f_Dest       ' COD_MITTENTE = Cod_Destinatario andata (Negozio)
            wsDest.Cells(rigaDest, 4).Value = f_RaggVero   ' MAGAZZINO_CARICO = Colonna 9
            wsDest.Cells(rigaDest, 5).Value = f_DataS      ' DATA_SCARICO = Colonna 3
            wsDest.Cells(rigaDest, 6).Value = 1            ' COD_DESTINATARIO = 1
            wsDest.Cells(rigaDest, 7).Value = "MAMONT"     ' MAGAZZINO_SCARICO = 'MAMONT'
            wsDest.Cells(rigaDest, 8).Value = 0            ' PESO = 0
            wsDest.Cells(rigaDest, 9).Value = 0            ' VOLUME = 0
            wsDest.Cells(rigaDest, 10).Value = 0           ' COLLI = 0
            
            rigaDest = rigaDest + 1
            
        End If
        
SaltaRiga:
    Next i
    
    ' Sposta la visualizzazione sul foglio finale per mostrarti il risultato compilato
    wsDest.Select
    
    Application.ScreenUpdating = True
    
  '  MsgBox "Elaborazione completata con successo sul foglio SGA_DEF_9!" & vbCrLf & _
  '         "Generate " & (rigaDest - 2) & " righe totali.", vbInformation, "Fine"
End Sub

