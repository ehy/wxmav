/**********************************************************************\
	Script for wxmav MSW binary installer program.
	Copyright (C) 2017 Ed Hynan covering modifications and
	additions in this derivative source.  This is "derivative"
	in that it is based on example source that is included with
	NSIS distribution.

	The licence for use of this source is an exception to the
	to the license generally covering the distribution that
	includes this source.  This source is covered by the same
	license covering the source from which it is derived, and
	of the '.nsh' sources that it includes with "!include";
	that license, current with this writing, is stated to be
	the "zlib/libpng license".  See:

		http://nsis.sourceforge.net/License

	That license covers both the '.in' form of the file, which is
	written to be processed with the POSIX 'm4' macro processor,
	and the output result of processing with m4.  (The '.m4' macro
	definitions file, "cdata.m4", is licensed under the GPLv2 or later,
	which must not be construed as altering the license covering the
	result of processing the input form of this file.)
\**********************************************************************/

# this is based on an NSIS example, which has the following comment:
;NSIS Modern User Interface
;Basic Example Script
;Written by Joost Verburg
#
# Note that the script language accepts comments introduced by
# semicolon or hash (and C-style comments that may span lines),
# so the ';' will be reserved for comments from the original example,
# and '#' used for new comments (and C comments to disable code, in
# particular original example code to be left in place for reference).
#

# Note that the multi-user setup follows the example at:
# http://nsis.sourceforge.net/Battle_for_Wesnoth

# MACROS to control variable attributes
  !define VERSION "1.0.0"
  !define INST_ROOT "WXMav 1.0.0"
  # EXEC_LVL: 'highest', 'admin', 'user'
  !define EXEC_LVL     highest
  !define SRC_ZIP      "wxmav-1.0.0.tar.gz"
  !define FILECLASS    "WXMav.File"
  !define FILEDESC     "WXMav (WX) M A/V Player Document"
  !define APP_SICO     "mav.ico"
  !define APP_VICO     "mav-varsz.ico"
  !define PATH_APP_SICO     ".\mav.ico"
  !define PATH_APP_VICO     ".\mav-varsz.ico"
  !define APP_ICO           "${APP_VICO}"
  !define PATH_APP_ICO      "${PATH_APP_VICO}"
  !define APP_BANNER     	".\banner-375x96.bmp"
  !define APP_BANNER_WI		375
  !define APP_BANNER_HI		96
  # name used in control panel add/remove reg key
  !define ADDREMNAME   "WXMav 1.0.0"
  # MSW registry H-key, e.g. HKCU or HKLM or multiuser SHCTX
  # (What's the "H" in HKLM, etc.? 'Hierarchy'?)
  !define _HK_         SHCTX
  ;!define _HK_         HKLM

  # macros to set-up/tear-down file extension -> icon/action association
  # Lifted from http://nsis.sourceforge.net/FileAssoc
  # Note key HKCR -- SHCTX apparently N.G.
  # 1) make file extension association
  !macro mk_file_association EXT FILECLASS DESCRIPTION ICON COMMANDTEXT COMMAND
   ; Backup the previously associated file class
   ReadRegStr $R0 HKCR ".${EXT}" ""
   WriteRegStr    HKCR ".${EXT}" "${FILECLASS}_backup" "$R0"
   WriteRegStr    HKCR ".${EXT}" "" "${FILECLASS}"
   WriteRegStr    HKCR "${FILECLASS}" "" '${DESCRIPTION}'
   WriteRegStr    HKCR "${FILECLASS}\DefaultIcon" "" '${ICON}'
   WriteRegStr    HKCR "${FILECLASS}\shell" "" "open"
   WriteRegStr    HKCR "${FILECLASS}\shell\open" "" '${COMMANDTEXT}'
   WriteRegStr    HKCR "${FILECLASS}\shell\open\command" "" '${COMMAND}'
  !macroend

  # 2) remove file extension association
  !macro rm_file_association EXT FILECLASS
   ; Backup the previously associated file class
   ReadRegStr $R0 HKCR ".${EXT}" '${FILECLASS}_backup'
   WriteRegStr    HKCR ".${EXT}" "" "$R0"
   DeleteRegKey   HKCR '${FILECLASS}'
  !macroend

# MACROS end

  CRCCheck on

  RequestExecutionLevel ${EXEC_LVL}

  !define MULTIUSER_EXECUTIONLEVEL Highest
  !define MULTIUSER_MUI "1"
  !define MULTIUSER_INSTALLMODE_COMMANDLINE "1"
  !define MULTIUSER_INSTALLMODE_DEFAULT_REGISTRY_KEY \
	"Software\GPLFreeSoftwareApplications\wxmav\1.0.0"
  !define MULTIUSER_INSTALLMODE_DEFAULT_REGISTRY_VALUENAME ""
  !define MULTIUSER_INSTALLMODE_INSTDIR_REGISTRY_KEY \
	"Software\GPLFreeSoftwareApplications\wxmav\1.0.0"
  !define MULTIUSER_INSTALLMODE_INSTDIR_REGISTRY_VALUENAME ""
  !define MULTIUSER_INSTALLMODE_INSTDIR	"${INST_ROOT}"

  !include "MultiUser.nsh"

;--------------------------------
;Include Modern UI

  !include "MUI2.nsh"

;--------------------------------
;Addl. file procs, for at least "EstimatedSize"

  !include "FileFunc.nsh"

;--------------------------------
;General

  ;Name and file
  Name "WXMav (WX) M A/V Player 1.0.0"
  OutFile "WXMav-1.0.0-install.exe"

# Added EH 0.0.4.4: suddenly seems necessary
  Icon "${PATH_APP_ICO}"

;--------------------------------
;Variables
  # orig. from example "StartMenu.nsi"
  Var StartMenuFolder

;--------------------------------
;Interface Settings

  # Added EH 1.0
  !define MUI_HEADERIMAGE
  !define MUI_HEADERIMAGE_BITMAP ${APP_BANNER}
  # orig
  !define MUI_WELCOMEFINISHPAGE_BITMAP mav.bmp
  !define MUI_UNWELCOMEFINISHPAGE_BITMAP vam.bmp
  !define MUI_ABORTWARNING

;--------------------------------
;Pages

  !insertmacro MUI_PAGE_WELCOME
  !insertmacro MUI_PAGE_LICENSE "..\LICENSE.gpl,v3"
  !insertmacro MUI_PAGE_COMPONENTS
  !insertmacro MULTIUSER_PAGE_INSTALLMODE
  !insertmacro MUI_PAGE_DIRECTORY

  # orig. from example "StartMenu.nsi"
  ;Start Menu Folder Page Configuration
  !define MUI_STARTMENUPAGE_REGISTRY_ROOT "${_HK_}"
  !define MUI_STARTMENUPAGE_REGISTRY_KEY \
	"Software\GPLFreeSoftwareApplications\wxmav\1.0.0"
  !define MUI_STARTMENUPAGE_REGISTRY_VALUENAME "Start Menu Folder"

  !insertmacro MUI_PAGE_STARTMENU Application $StartMenuFolder
  # End orig. from example "StartMenu.nsi"

  !insertmacro MUI_PAGE_INSTFILES
  !insertmacro MUI_PAGE_FINISH

  # uninstall pages
  !insertmacro MUI_UNPAGE_WELCOME
  !insertmacro MUI_UNPAGE_CONFIRM
  !insertmacro MUI_UNPAGE_INSTFILES
  !insertmacro MUI_UNPAGE_FINISH

;--------------------------------
;Languages

  !insertmacro MUI_LANGUAGE "English" ;first is the default
  #!insertmacro MUI_LANGUAGE "French"
  #!insertmacro MUI_LANGUAGE "German"
  #!insertmacro MUI_LANGUAGE "Spanish"
  # add more as clue-bulb illuminates

;--------------------------------
;Installer Sections

Section "WXMav program" SecExe

  SetOutPath "$INSTDIR"

  ;ADD YOUR OWN FILES HERE...
  # Added EH:
  File "..\wxmav.pyw"
  # Added EH 1.0:
  File "${PATH_APP_ICO}"

  ;Store installation folder
  WriteRegStr ${_HK_} "Software\GPLFreeSoftwareApplications\wxmav\1.0.0" \
	"" "$INSTDIR"
  WriteRegStr ${_HK_} "Software\GPLFreeSoftwareApplications\wxmav\1.0.0" \
	"installation directory" "$INSTDIR"
  WriteRegStr ${_HK_} "Software\GPLFreeSoftwareApplications\wxmav\1.0.0" \
	"installed version string" "1.0.0"
  WriteRegDWORD ${_HK_} "Software\GPLFreeSoftwareApplications\wxmav\1.0.0" \
	"installed version integer" 16777216
  WriteRegStr ${_HK_} "Software\GPLFreeSoftwareApplications\wxmav\1.0.0" \
	"installed executable file" "$INSTDIR\wxmav.pyw"
  # Added EH 0.0.4.4:
  WriteRegStr ${_HK_} "Software\GPLFreeSoftwareApplications\wxmav\1.0.0\DefaultIcon" \
    "installed icon" "$INSTDIR\${APP_ICO}"
  WriteRegStr ${_HK_} "Software\GPLFreeSoftwareApplications\wxmav\1.0.0" \
	"installed uninstall program" "$INSTDIR\uninstall.exe"

  WriteUninstaller "$INSTDIR\uninstall.exe"

  # orig. from example "StartMenu.nsi"
  !insertmacro MUI_STARTMENU_WRITE_BEGIN Application

  ;Create shortcuts
  CreateDirectory "$SMPROGRAMS\$StartMenuFolder"
  CreateShortCut "$SMPROGRAMS\$StartMenuFolder\WXMav.lnk" \
  	"$INSTDIR\wxmav.pyw"
  CreateShortCut "$SMPROGRAMS\$StartMenuFolder\Uninstall.lnk" \
  	"$INSTDIR\uninstall.exe"

  !insertmacro MUI_STARTMENU_WRITE_END
  # End orig. from example "StartMenu.nsi"

  # use macros {mk,rm}_file_association
  !insertmacro mk_file_association "pls" \
      "${FILECLASS}" "${FILEDESC}" "$INSTDIR\${APP_ICO}" \
      "Open with WXMav" "$INSTDIR\wxmav.pyw $\"%1$\""

  # This should make an entry in MSW control panel "Add/Remove Software"
  # from example at:
  #		http://nsis.sourceforge.net/Add_uninstall_information_to_Add/Remove_Programs
  WriteRegStr ${_HK_} \
	"Software\Microsoft\Windows\CurrentVersion\Uninstall\${ADDREMNAME}" \
     "DisplayName" "WXMav - WXMav (WX) M A/V Player"
  WriteRegStr ${_HK_} \
	"Software\Microsoft\Windows\CurrentVersion\Uninstall\${ADDREMNAME}" \
     "Publisher" "GPLFreeSoftwareApplications"
  WriteRegStr ${_HK_} \
	"Software\Microsoft\Windows\CurrentVersion\Uninstall\${ADDREMNAME}" \
     "DisplayVersion" "1.0.0"
  WriteRegDWORD ${_HK_} \
	"Software\Microsoft\Windows\CurrentVersion\Uninstall\${ADDREMNAME}" \
     "NoModify" 1
  WriteRegDWORD ${_HK_} \
	"Software\Microsoft\Windows\CurrentVersion\Uninstall\${ADDREMNAME}" \
     "NoRepair" 1
  ; missing before 0.0.4.5: switch /$MultiUser.InstallMode
  WriteRegStr ${_HK_} \
	"Software\Microsoft\Windows\CurrentVersion\Uninstall\${ADDREMNAME}" \
    "UninstallString" "$\"$INSTDIR\uninstall.exe$\" /$MultiUser.InstallMode"
  ; QuietUninstallString and EstimatedSize added with version 0.0.4.5
  WriteRegStr ${_HK_} \
	"Software\Microsoft\Windows\CurrentVersion\Uninstall\${ADDREMNAME}" \
    "QuietUninstallString" "$\"$INSTDIR\uninstall.exe$\" /$MultiUser.InstallMode /S"
  ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
  IntFmt $0 "0x%08X" $0
  WriteRegDWORD ${_HK_} \
	"Software\Microsoft\Windows\CurrentVersion\Uninstall\${ADDREMNAME}" \
    "EstimatedSize" "$0"

SectionEnd

#Section "appclass help documents" SecDoc
#
#  SetOutPath "$INSTDIR\mswhelpdir"
#
#  File "..\doc\help.zip"
#  File "..\doc\appname.pdf"
#
#  ;Store installation folder
#  WriteRegStr ${_HK_} "Software\vendorname\appname\appversion" \
#	"installed help documents" "$INSTDIR\mswhelpdir\help.zip"
#  WriteRegStr ${_HK_} "Software\vendorname\appname\appversion" \
#	"installed help PDF file" "$INSTDIR\mswhelpdir\appname.pdf"
#
#SectionEnd
#
#Section "appclass translations" SecI18n
#
#  !include i18n-sect
#
#SectionEnd

Section "WXMav source archive" SecSrc

  SetOutPath "$INSTDIR\Source Code"

  File "..\${SRC_ZIP}"

  ;Store installation folder
  WriteRegStr ${_HK_} "Software\GPLFreeSoftwareApplications\wxmav\1.0.0" \
	"installed source archive" \
	"$INSTDIR\Source Code\${SRC_ZIP}"

SectionEnd

Section "WXMav examples" SecExa

  SetOutPath "$INSTDIR\Examples"

  # Hmphh... cannot use '*.*' as a glob pattern if it's meant
  # to really require a '.' -- apparently nsis takes it as a
  # token equivalent to '*', because it is including "Makefile".
  # So, will have to give extensions individually (still better
  # than each file individually).
  #File /a "..\examples\*.*"
  File  "..\examples\*.pls"

  ;Store installation folder
  WriteRegStr ${_HK_} "Software\GPLFreeSoftwareApplications\wxmav\1.0.0" \
	"installed examples" \
    "$INSTDIR\Examples\(*.pls)"

SectionEnd

;--------------------------------
;Installer Functions

Function .onInit
  ;SetRegView 64
  !insertmacro MULTIUSER_INIT
  !insertmacro MUI_LANGDLL_DISPLAY
FunctionEnd

# after successful install offer to start program,
# and notify MSW shell of .pse extension change.
# this is a callback hook on nsis internal event
Function .onInstSuccess
  # from discussion at:
  # http://forums.winamp.com/showthread.php?s=&threadid=140254
  System::Call \
	'shell32.dll::SHChangeNotify(i, i, i, i) v (0x08000000, 0, 0, 0)'
  # query user w/ offer to start
  MessageBox MB_YESNO \
	"Would you like to start WXMav now?" \
	IDNO no_do_not_invoke_the_program
  Exec '"$INSTDIR\wxmav.pyw" "$INSTDIR\Examples\*.pls"'
  no_do_not_invoke_the_program:
FunctionEnd
# end func


;--------------------------------
;Descriptions

  ;Language strings
  LangString DESC_SecExe ${LANG_ENGLISH} \
	"The main program executable file (wxmav.pyw)."

#  LangString DESC_SecDoc ${LANG_ENGLISH} \
#	"The program help files."
#
#  LangString DESC_SecI18n ${LANG_ENGLISH} \
#	"The program translation files (not all locales have translations)."

  LangString DESC_SecSrc ${LANG_ENGLISH} \
	"The program source code (optional; free under GPL license)."

  LangString DESC_SecExa ${LANG_ENGLISH} \
	"Examples for WXMav, same .pls files ready to play and edit."

  ;Assign language strings to sections
  !insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
    !insertmacro MUI_DESCRIPTION_TEXT ${SecExe} $(DESC_SecExe)
#    !insertmacro MUI_DESCRIPTION_TEXT ${SecDoc} $(DESC_SecDoc)
#    !insertmacro MUI_DESCRIPTION_TEXT ${SecI18n} $(DESC_SecI18n)
    !insertmacro MUI_DESCRIPTION_TEXT ${SecSrc} $(DESC_SecSrc)
    !insertmacro MUI_DESCRIPTION_TEXT ${SecExa} $(DESC_SecExa)
  !insertmacro MUI_FUNCTION_DESCRIPTION_END

;--------------------------------
;Uninstaller Section

Section "Uninstall"

  # ASSOC.: from FAQ, to make MS style file associations
  # As of 0.0.4.5 use macro rm_file_association
  !insertmacro rm_file_association "pls" "${FILECLASS}"

  #Delete "$INSTDIR\mswhelpdir\help.zip"
  #Delete "$INSTDIR\mswhelpdir\appname.pdf"
  #Delete "$INSTDIR\en\appname.mo"
  #Delete "$INSTDIR\en_US\appname.mo"
  Delete "$INSTDIR\Source Code\${SRC_ZIP}"
  #Delete "$INSTDIR\mswxmpldir\anim-example\*"
  #RMDir  "$INSTDIR\mswxmpldir\anim-example"
  Delete "$INSTDIR\Examples\*.*"
  Delete "$INSTDIR\wxmav.pyw"
  Delete "$INSTDIR\${APP_ICO}"
  Delete "$INSTDIR\uninstall.exe"

  RMDir "$INSTDIR\Help Documents"
  #RMDir "$INSTDIR\en"
  #RMDir "$INSTDIR\en_US"
  RMDir "$INSTDIR\Source Code"
  RMDir "$INSTDIR\Examples"
  RMDir "$INSTDIR"

  # orig. from example "StartMenu.nsi"
  !insertmacro MUI_STARTMENU_GETFOLDER Application $StartMenuFolder

  Delete "$SMPROGRAMS\$StartMenuFolder\Uninstall.lnk"
  Delete "$SMPROGRAMS\$StartMenuFolder\WXMav.lnk"
  RMDir "$SMPROGRAMS\$StartMenuFolder"
  # End orig. from example "StartMenu.nsi"

  # Note next unconditional (no /ifempty) removal at version -- things
  # like window placement will be lost -- maybe revisit this in future
  DeleteRegKey          ${_HK_} "Software\GPLFreeSoftwareApplications\wxmav\1.0.0\MainWindow"
  DeleteRegKey          ${_HK_} "Software\GPLFreeSoftwareApplications\wxmav\1.0.0"
  DeleteRegKey /ifempty ${_HK_} "Software\GPLFreeSoftwareApplications\wxmav"
  #DeleteRegKey          ${_HK_} "Software\vendorname\appname"
  DeleteRegKey /ifempty ${_HK_} "Software\GPLFreeSoftwareApplications"
  # this removes the control panel "Add/Remove" entry
  DeleteRegKey          ${_HK_} \
	"Software\Microsoft\Windows\CurrentVersion\Uninstall\${ADDREMNAME}"

SectionEnd

;--------------------------------
;Uninstaller Functions

Function un.onInit
  !insertmacro MULTIUSER_UNINIT
  !insertmacro MUI_UNGETLANGUAGE
FunctionEnd

# after successful uninstall,
# and notify MSW shell of .pse extension change.
# this is a callback hook on nsis internal event
Function un.onUninstSuccess
  # from discussion at:
  # http://forums.winamp.com/showthread.php?s=&threadid=140254
  System::Call \
	'shell32.dll::SHChangeNotify(i, i, i, i) v (0x08000000, 0, 0, 0)'
FunctionEnd
# end func

