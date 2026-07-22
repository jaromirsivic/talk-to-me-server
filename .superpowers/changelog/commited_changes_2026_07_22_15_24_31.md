# Commitnuté změny

- Windows řídicí skripty byly sjednoceny přes `server-control.ps1` a ověřují vztah mezi PID souborem, procesním stromem a vlastníkem portu.
- Linuxové a macOS skripty používají `lsof` nebo `ss` k ověření vlastníka naslouchajícího portu.
- Start odmítne cizího vlastníka portu místo falešného úspěchu a Stop ukončí pouze ověřený projektový procesní strom.
- Doplněny regresní smoke testy a ověřena syntaxe PowerShellu i POSIX shellu.
