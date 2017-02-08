# -*- coding: utf-8 -*-
#
# codimension - graphics python two-way code editor and analyzer
# Copyright (C) 2010-2017  Sergey Satskiy <sergey.satskiy@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

#
# The file was taken from eric 4.4.3 and adopted for codimension.
# Original copyright:
# Copyright (c) 2007 - 2010 Detlev Offenbach <detlev@die-offenbachs.de>
#

"""Find and replace widgets implementation"""

from utils.pixmapcache import getIcon
from utils.globals import GlobalData
from utils.project import CodimensionProject
from .qt import (QHBoxLayout, QToolButton, QLabel, QSizePolicy, QComboBox,
                 QGridLayout, QWidget, QCheckBox, QKeySequence, Qt, QSize,
                 QEvent, pyqtSignal)
from .mainwindowtabwidgetbase import MainWindowTabWidgetBase


class ComboBoxNoUndo(QComboBox):

    """Combo box which allows application wide Ctrl+Z etc."""

    def __init__(self, parent=None):
        QComboBox.__init__(self, parent)
        self.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLength)

    def event(self, event):
        """Skips the Undo/Redo shortcuts.
           They should be processed by the editor
        """
        if event.type() == QEvent.ShortcutOverride:
            if event.matches(QKeySequence.Undo):
                return False
            if event.matches(QKeySequence.Redo):
                return False
        return QComboBox.event(self, event)


class SearchAttr:

    """Stores search attributes for a single editor"""

    def __init__(self):
        self.line = -1
        self.pos = -1
        self.firstLine = -1
        self.match = [-1, -1, -1]     # line, pos, length


class SearchSupport:

    """Auxiliary class to support incremental search"""

    def __init__(self):
        self.editorSearchAttributes = {}

    def add(self, uuid, searchAttr):
        """Adds new editor search attributes"""
        self.editorSearchAttributes[uuid] = searchAttr

    def hasEditor(self, uuid):
        """Checks if there was a search in the editor"""
        return uuid in self.editorSearchAttributes

    def get(self, uuid):
        """Provides the search attributes"""
        return self.editorSearchAttributes[uuid]

    def delete(self, uuid):
        """Deletes the editor attributes from the storage"""
        if self.hasEditor(uuid):
            del self.editorSearchAttributes[uuid]

    def clearStartPositions(self):
        """Cleans up the memorised start positions"""
        for key in self.editorSearchAttributes:
            attributes = self.editorSearchAttributes[key]
            attributes.line = -1
            attributes.pos = -1
            self.editorSearchAttributes[key] = attributes


class FindReplaceBase(QWidget):

    """Base class for both find and replace widgets"""

    maxHistory = 32
    incSearchDone = pyqtSignal(bool)

    def __init__(self, editorsManager, parent=None):
        QWidget.__init__(self, parent)
        self._skip = True

        self.editorsManager = editorsManager
        self._currentWidget = None
        self._isTextEditor = False
        self._editor = None
        self._editorUUID = False
        self.findHistory = GlobalData().project.findHistory
        self._findBackward = False

        # Incremental search support
        self._searchSupport = SearchSupport()
        editorsManager.sigTabClosed.connect(self.__onTabClosed)

        # Common graphics items
        self.closeButton = QToolButton(self)
        self.closeButton.setToolTip("Close the dialog (ESC)")
        self.closeButton.setIcon(getIcon("close.png"))
        self.closeButton.clicked.connect(self.hide)

        self.findLabel = QLabel(self)
        self.findLabel.setText("Find:")

        self.findtextCombo = ComboBoxNoUndo(self)
        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(
            self.findtextCombo.sizePolicy().hasHeightForWidth())
        self.findtextCombo.setSizePolicy(sizePolicy)
        self.findtextCombo.setEditable(True)
        self.findtextCombo.setInsertPolicy(QComboBox.InsertAtTop)
        self.findtextCombo.setCompleter(None)
        self.findtextCombo.setDuplicatesEnabled(False)
        self.findtextCombo.setEnabled(False)
        self.findtextCombo.editTextChanged.connect(self._onEditTextChanged)

        self.findPrevButton = QToolButton(self)
        self.findPrevButton.setToolTip("Previous occurrence (Shift+F3)")
        self.findPrevButton.setIcon(getIcon("1leftarrow.png"))
        self.findPrevButton.setIconSize(QSize(24, 16))
        self.findPrevButton.setFocusPolicy(Qt.NoFocus)
        self.findPrevButton.setEnabled(False)

        self.findNextButton = QToolButton(self)
        self.findNextButton.setToolTip("Next occurrence (F3)")
        self.findNextButton.setIcon(getIcon("1rightarrow.png"))
        self.findNextButton.setIconSize(QSize(24, 16))
        self.findNextButton.setFocusPolicy(Qt.NoFocus)
        self.findNextButton.setEnabled(False)

        self.caseCheckBox = QCheckBox(self)
        self.caseCheckBox.setText("Match case")
        self.caseCheckBox.setFocusPolicy(Qt.NoFocus)
        self.caseCheckBox.setEnabled(False)
        self.caseCheckBox.stateChanged.connect(self._onCheckBoxChange)

        self.wordCheckBox = QCheckBox(self)
        self.wordCheckBox.setText("Whole word")
        self.wordCheckBox.setFocusPolicy(Qt.NoFocus)
        self.wordCheckBox.setEnabled(False)
        self.wordCheckBox.stateChanged.connect(self._onCheckBoxChange)

        self.regexpCheckBox = QCheckBox(self)
        self.regexpCheckBox.setText("Regexp")
        self.regexpCheckBox.setFocusPolicy(Qt.NoFocus)
        self.regexpCheckBox.setEnabled(False)
        self.regexpCheckBox.stateChanged.connect(self._onCheckBoxChange)

        self.findtextCombo.lineEdit().returnPressed.connect(
            self.__findByReturnPressed)
        self._skip = False

    def keyPressEvent(self, event):
        """Handles the ESC key for the search bar"""
        if event.key() == Qt.Key_Escape:
            self._searchSupport.clearStartPositions()
            event.accept()
            self.hide()
            activeWindow = self.editorsManager.currentWidget()
            if activeWindow:
                activeWindow.setFocus()

    def __onTabClosed(self, uuid):
        """Triggered when a tab is closed"""
        self._searchSupport.delete(uuid)

    def setFocus(self):
        """Overridded setFocus"""
        self.findtextCombo.lineEdit().selectAll()
        self.findtextCombo.setFocus()

    def show(self, text=''):
        """Overridden show() method"""
        self._skip = True
        self.findtextCombo.clear()
        self.findtextCombo.addItems(self.findHistory)
        self.findtextCombo.setEditText(text)
        self.findtextCombo.lineEdit().selectAll()
        self.regexpCheckBox.setChecked(False)
        self.findtextCombo.setFocus()
        self._findBackward = False
        self._skip = False

        QWidget.show(self)
        self.activateWindow()

        self._performSearch(True)

    def startHiddenSearch(self, text):
        """Initiates search without activating the widget"""
        self._skip = True
        self.findtextCombo.clear()
        self.findtextCombo.addItems(self.findHistory)
        self.findtextCombo.setEditText(text)
        self.findtextCombo.lineEdit().selectAll()
        self.regexpCheckBox.setChecked(False)
        self._findBackward = False
        self._skip = False

        self._performSearch(True)

    def updateStatus(self):
        """Triggered when the current tab is changed"""
        # Memorize the current environment
        self._currentWidget = self.editorsManager.currentWidget()
        self._isTextEditor = self._currentWidget.getType() in \
                                [MainWindowTabWidgetBase.PlainTextEditor,
                                 MainWindowTabWidgetBase.VCSAnnotateViewer]
        if self._isTextEditor:
            self._editor = self._currentWidget.getEditor()
            self._editorUUID = self._currentWidget.getUUID()
        else:
            self._editor = None
            self._editorUUID = ""

        self.findtextCombo.setEnabled(self._isTextEditor)

        textAvailable = self.findtextCombo.currentText() != ""
        self.findPrevButton.setEnabled(self._isTextEditor and textAvailable)
        self.findNextButton.setEnabled(self._isTextEditor and textAvailable)

        self.caseCheckBox.setEnabled(self._isTextEditor)
        self.wordCheckBox.setEnabled(self._isTextEditor)
        self.regexpCheckBox.setEnabled(self._isTextEditor)

    def _resetHighlightOtherEditors(self, uuid):
        """Resets all the highlights in other editors except of the given"""
        searchAttributes = None
        if self._searchSupport.hasEditor(uuid):
            searchAttributes = self._searchSupport.get(uuid)

        for key in self._searchSupport.editorSearchAttributes:
            if key == uuid:
                continue
            widget = self.editorsManager.getWidgetByUUID(key)
            if widget is None:
                continue
            editor = widget.getEditor()
            editor.clearSearchIndicators()

        # Clear what is memorized about the other editors
        self._searchSupport.editorSearchAttributes = {}

        if searchAttributes is not None:
            self._searchSupport.add(uuid, searchAttributes)

    def _onCheckBoxChange(self, newState):
        """Triggered when a search check box state is changed"""
        if not self._skip:
            self._resetHighlightOtherEditors(self._editorUUID)
            self._performSearch(False)

    def _onEditTextChanged(self, text):
        """Triggered when the search text has been changed"""
        if not self._skip:
            self._resetHighlightOtherEditors(self._editorUUID)
            self._performSearch(False)

    def _performSearch(self, fromScratch):
        """Performs the incremental search"""
        if not self._isTextEditor:
            return

        # Memorize the search arguments
        text = self.findtextCombo.currentText()
        isRegexp = self.regexpCheckBox.isChecked()
        isCase = self.caseCheckBox.isChecked()
        isWord = self.wordCheckBox.isChecked()

        status = text != ""
        self.findNextButton.setEnabled(status)
        self.findPrevButton.setEnabled(status)

        if fromScratch:
            self._searchSupport.delete(self._editorUUID)
        self._initialiseSearchAttributes(self._editorUUID)
        searchAttributes = self._searchSupport.get(self._editorUUID)

        if not fromScratch:
            # We've been searching here already
            if text == "":
                # Remove the highlight and scroll back
                self._editor.clearAllIndicators(self._editor.searchIndicator)
                self._editor.clearAllIndicators(self._editor.matchIndicator)

                self._editor.cursorPosition = searchAttributes.line, \
                                              searchAttributes.pos
                self._editor.ensureLineOnScreen(searchAttributes.firstLine)
                searchAttributes.match = [-1, -1, -1]
                self.incSearchDone.emit(False)
                return

            matchTarget = self._editor.highlightMatch(text,
                                                      searchAttributes.line,
                                                      searchAttributes.pos,
                                                      isRegexp, isCase,
                                                      isWord)
            searchAttributes.match = matchTarget
            if matchTarget != [-1, -1, -1]:
                # Select the match starting from the end. This will move the
                # cursor to the beginnig of the match.
                tgtPos = self._editor.positionFromLineIndex(matchTarget[0],
                                                            matchTarget[1])
                eLine, ePos = self._editor.lineIndexFromPosition(
                    tgtPos + matchTarget[2])
                self._editor.setSelection(eLine, ePos,
                                          matchTarget[0], matchTarget[1])
                self._editor.ensureLineOnScreen(matchTarget[0])
                self.incSearchDone.emit(True)
            else:
                # Nothing is found, so scroll back to the original
                self._editor.cursorPosition = searchAttributes.line, \
                                              searchAttributes.pos
                self._editor.ensureLineOnScreen(searchAttributes.firstLine)
                self.incSearchDone.emit(False)

            return

        # Brand new editor to search in
        if text == "":
            self.incSearchDone.emit(False)
            return

        matchTarget = self._editor.highlightMatch(text,
                                                  searchAttributes.line,
                                                  searchAttributes.pos,
                                                  isRegexp, isCase, isWord)
        searchAttributes.match = matchTarget
        self._searchSupport.add(self._editorUUID, searchAttributes)

        if matchTarget != [-1, -1, -1]:
            # Select the match starting from the end. This will move the
            # cursor to the beginnig of the match.
            tgtPos = self._editor.positionFromLineIndex(matchTarget[0],
                                                        matchTarget[1])
            eLine, ePos = self._editor.lineIndexFromPosition(tgtPos +
                                                             matchTarget[2])
            self._editor.setSelection(eLine, ePos,
                                      matchTarget[0], matchTarget[1])
            self._editor.ensureLineOnScreen(matchTarget[0])
            self.incSearchDone.emit(True)
            return

        self.incSearchDone.emit(False)

    def _initialiseSearchAttributes(self, uuid):
        """Creates a record if none existed"""
        if self._searchSupport.hasEditor(uuid):
            return

        searchAttributes = SearchAttr()
        searchAttributes.line = self._currentWidget.getLine()
        searchAttributes.pos = self._currentWidget.getPos()
        searchAttributes.firstLine = self._editor.firstVisibleLine()

        searchAttributes.match = [-1, -1, -1]
        self._searchSupport.add(uuid, searchAttributes)

    def _advanceMatchIndicator(self, uuid, newLine, newPos, newLength):
        """Advances the current match indicator for the given editor"""
        if not self._searchSupport.hasEditor(uuid):
            return

        searchAttributes = self._searchSupport.get(uuid)
        match = searchAttributes.match

        widget = self.editorsManager.getWidgetByUUID(uuid)
        if widget is None:
            return
        editor = widget.getEditor()

        # Replace the old highlight
        if searchAttributes.match != [-1, -1, -1]:
            tgtPos = editor.positionFromLineIndex(match[0], match[1])
            editor.clearIndicatorRange(editor.matchIndicator,
                                       tgtPos, match[2])
            editor.setIndicatorRange(editor.searchIndicator,
                                     tgtPos, match[2])

        # Memorise new target
        searchAttributes.match = [newLine, newPos, newLength]
        self._searchSupport.add(uuid, searchAttributes)

        # Update the new highlight
        tgtPos = editor.positionFromLineIndex(newLine, newPos)
        editor.clearIndicatorRange(editor.searchIndicator, tgtPos, newLength)
        editor.setIndicatorRange(editor.matchIndicator, tgtPos, newLength)

        # Select the match from end to the start - this will move the
        # cursor to the first symbol of the match
        eLine, ePos = editor.lineIndexFromPosition(tgtPos + newLength)
        editor.setSelection(eLine, ePos, newLine, newPos)

        # Move the cursor to the new match
        editor.ensureLineOnScreen(newLine)

    def onNext(self, clearSBMessage=True):
        """Triggered when the find next is clicked"""
        if not self.onPrevNext():
            return

        self._findBackward = False
        if not self.__findNextPrev(clearSBMessage):
            GlobalData().mainWindow.showStatusBarMessage("No matches found", 0)
            self.incSearchDone.emit(False)
        else:
            self.incSearchDone.emit(True)

    def onPrev(self, clearSBMessage=True):
        """Triggered when the find prev is clicked"""
        if not self.onPrevNext():
            return

        self._findBackward = True
        if not self.__findNextPrev(clearSBMessage):
            GlobalData().mainWindow.showStatusBarMessage("No matches found", 0)
            self.incSearchDone.emit(False)
        else:
            self.incSearchDone.emit(True)

    def onPrevNext(self):
        """Checks prerequisites, saves the history and
           returns True if the search should be done
        """
        txt = self.findtextCombo.currentText()
        if txt == "":
            return False

        currentWidget = self.editorsManager.currentWidget()
        return currentWidget.getType() in \
            [MainWindowTabWidgetBase.PlainTextEditor,
             MainWindowTabWidgetBase.VCSAnnotateViewer]

    def __findByReturnPressed(self):
        """Triggered when 'Enter' or 'Return' is clicked"""
        if self._findBackward:
            self.onPrev()
        else:
            self.onNext()

    def __findNextPrev(self, clearSBMessage=True):
        """Finds the next occurrence of the search text"""
        if not self._isTextEditor:
            return False

        # Identify the search start point
        startLine = self._currentWidget.getLine()
        startPos = self._currentWidget.getPos()

        if self._searchSupport.hasEditor(self._editorUUID):
            searchAttributes = self._searchSupport.get(self._editorUUID)
            if startLine == searchAttributes.match[0] and \
               startPos == searchAttributes.match[1]:
                # The cursor is on the current match, i.e. the user did not
                # put the focus into the editor and did not move it
                if not self._findBackward:
                    # The match[ 2 ] gives the length in bytes, not in chars
                    # which could be national i.e. multibytes. So calc the
                    # right length in chars...
                    pos = self._editor.positionFromLineIndex(startLine,
                                                             startPos)
                    adjustment = len(self._editor.stringAt(
                        pos, searchAttributes.match[2]))
                    startPos = startPos + adjustment
            else:
                # The cursor is not at the same position as the last match,
                # i.e. the user moved it some way
                # Update the search attributes as if a new search is started
                searchAttributes.line = startLine
                searchAttributes.pos = startPos
                searchAttributes.firstLine = self._editor.firstVisibleLine()
                searchAttributes.match = [-1, -1, -1]
                self._searchSupport.add(self._editorUUID, searchAttributes)
        else:
            # There were no search in this editor
            searchAttributes = SearchAttr()
            searchAttributes.line = startLine
            searchAttributes.pos = startPos
            searchAttributes.firstLine = self._editor.firstVisibleLine()
            searchAttributes.match = [-1, -1, -1]
            self._searchSupport.add(self._editorUUID, searchAttributes)

        # Here: start point has been identified
        if self.__searchFrom(startLine, startPos, clearSBMessage):
            # Something new has been found - change the start pos
            searchAttributes = self._searchSupport.get(self._editorUUID)
            searchAttributes.line = self._currentWidget.getLine()
            searchAttributes.pos = self._currentWidget.getPos()
            searchAttributes.firstLine = self._editor.firstVisibleLine()
            self._searchSupport.add(self._editorUUID, searchAttributes)
            return True
        return False

    def __searchFrom(self, startLine, startPos, clearSBMessage=True):
        """Searches starting from the given position"""
        # Memorize the search arguments
        text = self.findtextCombo.currentText()
        isRegexp = self.regexpCheckBox.isChecked()
        isCase = self.caseCheckBox.isChecked()
        isWord = self.wordCheckBox.isChecked()

        if not self._findBackward:
            # Search forward
            self._editor.highlightMatch(text, startLine, startPos, isRegexp,
                                        isCase, isWord, False, False)
            targets = self._editor.getTargets(text, isRegexp, isCase, isWord,
                                              startLine, startPos, -1, -1)
            if len(targets) == 0:
                GlobalData().mainWindow.showStatusBarMessage(
                    "Reached the end of the document. "
                    "Searching from the beginning...")
                targets = self._editor.getTargets(text,
                                                  isRegexp, isCase, isWord,
                                                  0, 0, startLine, startPos)
                if len(targets) == 0:
                    searchAttributes = self._searchSupport.get(
                        self._editorUUID)
                    searchAttributes.match = [-1, -1, -1]
                    self._searchSupport.add(self._editorUUID,
                                            searchAttributes)
                    return False    # Nothing has matched
            else:
                if clearSBMessage:
                    # Hide the 'reached the end of ...' message
                    GlobalData().mainWindow.clearStatusBarMessage(0)

            # Move the highlight and the cursor to the new match and
            # memorize a new match
            self._advanceMatchIndicator(self._editorUUID,
                                        targets[0][0], targets[0][1],
                                        targets[0][2])
            return True

        # Search backward
        self._editor.highlightMatch(text, startLine, startPos,
                                    isRegexp, isCase, isWord, False, False)
        targets = self._editor.getTargets(text, isRegexp, isCase, isWord,
                                          0, 0, startLine, startPos)
        if len(targets) == 0:
            GlobalData().mainWindow.showStatusBarMessage(
                "Reached the beginning of the document. "
                "Searching from the end...")
            targets = self._editor.getTargets(text, isRegexp, isCase, isWord,
                                              startLine, startPos, -1, -1)
            if len(targets) == 0:
                searchAttributes = self._searchSupport.get(self._editorUUID)
                searchAttributes.match = [-1, -1, -1]
                self._searchSupport.add(self._editorUUID, searchAttributes)
                return False    # Nothing has matched
        else:
            if clearSBMessage:
                # Hide the 'reached the beginning of ...' message
                GlobalData().mainWindow.clearStatusBarMessage(0)

        # Move the highlight and the cursor to the new match and
        # memorize a new match
        index = len(targets) - 1
        self._advanceMatchIndicator(self._editorUUID,
                                    targets[index][0], targets[index][1],
                                    targets[index][2])
        return True

    def _addToHistory(self, combo, history, text):
        """Adds the item to the history. Returns true if need to add."""
        changes = False

        if text in history:
            if history[0] != text:
                changes = True
                history.remove(text)
                history.insert(0, text)
        else:
            changes = True
            history.insert(0, text)

        if len(history) > self.maxHistory:
            changes = True
            history = history[:self.maxHistory]

        self._skip = True
        combo.clear()
        combo.addItems(history)
        self._skip = False
        return changes

    def getLastSearchString(self):
        """Provides the string which was searched last time"""
        return self.findtextCombo.currentText()


class FindWidget(FindReplaceBase):

    """Find in the current file widget"""

    def __init__(self, editorsManager, parent=None):
        FindReplaceBase.__init__(self, editorsManager, parent)

        self.horizontalLayout = QHBoxLayout(self)
        self.horizontalLayout.setContentsMargins(0, 0, 0, 0)

        self.horizontalLayout.addWidget(self.closeButton)
        self.horizontalLayout.addWidget(self.findLabel)
        self.horizontalLayout.addWidget(self.findtextCombo)
        self.horizontalLayout.addWidget(self.findPrevButton)
        self.horizontalLayout.addWidget(self.findNextButton)
        self.horizontalLayout.addWidget(self.caseCheckBox)
        self.horizontalLayout.addWidget(self.wordCheckBox)
        self.horizontalLayout.addWidget(self.regexpCheckBox)

        self.setTabOrder(self.findtextCombo, self.caseCheckBox)
        self.setTabOrder(self.caseCheckBox, self.wordCheckBox)
        self.setTabOrder(self.wordCheckBox, self.regexpCheckBox)
        self.setTabOrder(self.regexpCheckBox, self.findNextButton)
        self.setTabOrder(self.findNextButton, self.findPrevButton)
        self.setTabOrder(self.findPrevButton, self.closeButton)

        GlobalData().project.sigProjectChanged.connect(self.__onProjectChanged)
        self.findNextButton.clicked.connect(self.onNext)
        self.findPrevButton.clicked.connect(self.onPrev)

    def __onProjectChanged(self, what):
        """Triggered when a project is changed"""
        if what == CodimensionProject.CompleteProject:
            self._skip = True
            self.findHistory = GlobalData().project.findHistory
            self.findtextCombo.setEditText("")
            self.findtextCombo.clear()
            self.findtextCombo.addItems(self.findHistory)
            self._skip = False

    def updateStatus(self):
        """Triggered when the current tab is changed"""
        FindReplaceBase.updateStatus(self)

    def onNext(self):
        """Triggered when the find next button is clicked"""
        FindReplaceBase.onNext(self)
        self.__updateFindHistory()

    def onPrev(self):
        """Triggered when the find previous button is clicked"""
        FindReplaceBase.onPrev(self)
        self.__updateFindHistory()

    def __updateFindHistory(self):
        """Updates the find history if required"""
        if self.findtextCombo.currentText() != "":
            if self._addToHistory(self.findtextCombo,
                                  self.findHistory,
                                  self.findtextCombo.currentText()):
                prj = GlobalData().project
                prj.setFindHistory(self.findHistory)


class ReplaceWidget(FindReplaceBase):

    """Find and replace in the current file widget"""

    def __init__(self, editorsManager, parent=None):
        FindReplaceBase.__init__(self, editorsManager, parent)
        self._skip = True
        prj = GlobalData().project
        self.findHistory = prj.findHistory
        self.replaceHistory = prj.replaceHistory

        # Additional UI elements
        self.replaceLabel = QLabel(self)
        self.replaceLabel.setText("Replace:")

        self.replaceCombo = ComboBoxNoUndo(self)

        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(
            self.replaceCombo.sizePolicy().hasHeightForWidth())
        self.replaceCombo.setSizePolicy(sizePolicy)
        self.replaceCombo.setEditable(True)
        self.replaceCombo.setInsertPolicy(QComboBox.InsertAtTop)
        self.replaceCombo.setCompleter(None)
        self.replaceCombo.setDuplicatesEnabled(False)
        self.replaceCombo.setEnabled(False)

        self.replaceButton = QToolButton(self)
        self.replaceButton.setToolTip("Replace current occurrence")
        self.replaceButton.setIcon(getIcon("replace.png"))
        self.replaceButton.setEnabled(False)
        self.replaceButton.clicked.connect(self.__onReplace)
        self.replaceButton.setIconSize(QSize(24, 16))

        self.replaceAllButton = QToolButton(self)
        self.replaceAllButton.setToolTip("Replace all occurrences")
        self.replaceAllButton.setIcon(getIcon("replace-all.png"))
        self.replaceAllButton.setIconSize(QSize(24, 16))
        self.replaceAllButton.setEnabled(False)
        self.replaceAllButton.clicked.connect(self.__onReplaceAll)

        self.replaceAndMoveButton = QToolButton(self)
        self.replaceAndMoveButton.setToolTip(
            "Replace current occurrence and move to the next match")
        self.replaceAndMoveButton.setIcon(getIcon("replace-move.png"))
        self.replaceAndMoveButton.setIconSize(QSize(24, 16))
        self.replaceAndMoveButton.setEnabled(False)
        self.replaceAndMoveButton.clicked.connect(self.__onReplaceAndMove)

        self.gridLayout = QGridLayout(self)
        self.gridLayout.setContentsMargins(0, 0, 0, 0)

        self.gridLayout.addWidget(self.closeButton, 0, 0, 1, 1)
        self.gridLayout.addWidget(self.findLabel, 0, 1, 1, 1)
        self.gridLayout.addWidget(self.findtextCombo, 0, 2, 1, 1)
        self.gridLayout.addWidget(self.findPrevButton, 0, 3, 1, 1)
        self.gridLayout.addWidget(self.findNextButton, 0, 4, 1, 1)
        self.gridLayout.addWidget(self.caseCheckBox, 0, 5, 1, 1)
        self.gridLayout.addWidget(self.wordCheckBox, 0, 6, 1, 1)
        self.gridLayout.addWidget(self.regexpCheckBox, 0, 7, 1, 1)

        self.gridLayout.addWidget(self.replaceLabel, 1, 1, 1, 1)
        self.gridLayout.addWidget(self.replaceCombo, 1, 2, 1, 1)
        self.gridLayout.addWidget(self.replaceButton, 1, 3, 1, 1)
        self.gridLayout.addWidget(self.replaceAndMoveButton, 1, 4, 1, 1)
        self.gridLayout.addWidget(self.replaceAllButton, 1, 5, 1, 1)

        self.setTabOrder(self.findtextCombo, self.replaceCombo)
        self.setTabOrder(self.replaceCombo, self.caseCheckBox)
        self.setTabOrder(self.caseCheckBox, self.wordCheckBox)
        self.setTabOrder(self.wordCheckBox, self.regexpCheckBox)
        self.setTabOrder(self.regexpCheckBox, self.findNextButton)
        self.setTabOrder(self.findNextButton, self.findPrevButton)
        self.setTabOrder(self.findPrevButton, self.replaceAndMoveButton)
        self.setTabOrder(self.replaceButton, self.replaceAllButton)
        self.setTabOrder(self.replaceAndMoveButton, self.replaceAllButton)
        self.setTabOrder(self.replaceAllButton, self.closeButton)

        GlobalData().project.sigProjectChanged.connect(self.__onProjectChanged)
        self.findNextButton.clicked.connect(self.onNext)
        self.findPrevButton.clicked.connect(self.onPrev)
        self.incSearchDone.connect(self.__onSearchDone)
        self.replaceCombo.editTextChanged.connect(self.__onReplaceTextChanged)
        self.replaceCombo.lineEdit().returnPressed.connect(
            self.__onReplaceAndMove)
        self.__connected = False
        self.__replaceCouldBeEnabled = False
        self._skip = False

    def updateStatus(self):
        """Triggered when the current tab is changed"""
        FindReplaceBase.updateStatus(self)
        if self._currentWidget.getType() == \
           MainWindowTabWidgetBase.VCSAnnotateViewer:
            self.findtextCombo.setEnabled(False)
            self.findPrevButton.setEnabled(False)
            self.findNextButton.setEnabled(False)
            self.caseCheckBox.setEnabled(False)
            self.wordCheckBox.setEnabled(False)
            self.regexpCheckBox.setEnabled(False)
            self.replaceCombo.setEnabled(False)
            self.replaceAllButton.setEnabled(False)
            self.replaceButton.setEnabled(False)
            self.replaceAndMoveButton.setEnabled(False)
            return

        self.__updateReplaceAllButtonStatus()

        if self._isTextEditor:
            self.__cursorPositionChanged()
        else:
            self.replaceButton.setEnabled(False)
            self.replaceAndMoveButton.setEnabled(False)
            self.__replaceCouldBeEnabled = False

        if self.__connected:
            self.__unsubscribeFromCursorChange()
        self.__subscribeToCursorChangePos()

    def __updateReplaceAllButtonStatus(self):
        """Updates the replace all button status"""
        self.replaceCombo.setEnabled(self._isTextEditor)
        textAvailable = self.findtextCombo.currentText() != ""
        self.replaceAllButton.setEnabled(self._isTextEditor and textAvailable)

    def show(self, text=''):
        """Overriden show method"""
        self._skip = True
        self.replaceCombo.clear()
        self.replaceCombo.addItems(self.replaceHistory)
        self.replaceCombo.setEditText('')
        self._skip = False

        FindReplaceBase.show(self, text)
        self.__subscribeToCursorChangePos()

    def hide(self):
        """Overriden hide method"""
        if self.__connected:
            self.__unsubscribeFromCursorChange()
        FindReplaceBase.hide(self)

    def __onProjectChanged(self, what):
        """Triggered when a project is changed"""
        if what == CodimensionProject.CompleteProject:
            prj = GlobalData().project
            self._skip = True
            self.findHistory = prj.findHistory
            self.findtextCombo.clear()
            self.findtextCombo.setEditText('')
            self.findtextCombo.addItems(self.findHistory)
            self.replaceHistory = prj.replaceHistory
            self.replaceCombo.clear()
            self.replaceCombo.setEditText('')
            self.replaceCombo.addItems(self.replaceHistory)
            self._skip = False

    def __onSearchDone(self, found):
        """Triggered when incremental search is done"""
        self.replaceButton.setEnabled(found)
        self.replaceAndMoveButton.setEnabled(found)
        self.replaceAllButton.setEnabled(found)
        self.__replaceCouldBeEnabled = True

    def __onReplaceTextChanged(self, text):
        """Triggered when replace with text is changed"""
        self.__updateReplaceAllButtonStatus()
        self.replaceButton.setEnabled(self.__replaceCouldBeEnabled)
        self.replaceAndMoveButton.setEnabled(self.__replaceCouldBeEnabled)

    def __subscribeToCursorChangePos(self):
        """Subscribes for the cursor position notification"""
        if self._editor is not None:
            self._editor.cursorPositionChanged.connect(
                self.__cursorPositionChanged)
            self.__connected = True

    def __unsubscribeFromCursorChange(self):
        """Unsubscribes from the cursor position notification"""
        if self._editor is not None:
            try:
                self._editor.cursorPositionChanged.disconnect(
                    self.__cursorPositionChanged)
            except:
                pass
            self.__connected = False

    def __cursorPositionChanged(self):
        """Triggered when the cursor position is changed"""
        if self._searchSupport.hasEditor(self._editorUUID):
            line, pos = self._editor.cursorPosition
            searchAttributes = self._searchSupport.get(self._editorUUID)
            enable = line == searchAttributes.match[0] and \
                     pos == searchAttributes.match[1]
        else:
            enable = False

        self.replaceButton.setEnabled(enable)
        self.replaceAndMoveButton.setEnabled(enable)
        self.__replaceCouldBeEnabled = enable

    def __onReplaceAll(self):
        """Triggered when replace all button is clicked"""
        text = self.findtextCombo.currentText()
        isRegexp = self.regexpCheckBox.isChecked()
        isCase = self.caseCheckBox.isChecked()
        isWord = self.wordCheckBox.isChecked()
        replaceText = self.replaceCombo.currentText()

        self.__updateReplaceHistory(text, replaceText)

        # Check that there is at least one target to replace
        found = self._editor.findFirstTarget(text,
                                             isRegexp, isCase, isWord, 0, 0)
        if not found:
            GlobalData().mainWindow.showStatusBarMessage(
                "No matches found. Nothing is replaced.")
            return

        # There is something matching
        count = 0
        self._editor.beginUndoAction()
        while found:
            self._editor.replaceTarget(str(replaceText))
            count += 1
            found = self._editor.findNextTarget()
        self._editor.endUndoAction()
        self.replaceButton.setEnabled(False)
        self.replaceAndMoveButton.setEnabled(False)
        self.__replaceCouldBeEnabled = False

        suffix = ""
        if count > 1:
            suffix = "s"
        GlobalData().mainWindow.showStatusBarMessage(
            str(count) + " occurrence" + suffix + " replaced.")
        GlobalData().mainWindow.clearStatusBarMessage(1)

    def __onReplace(self):
        """Triggered when replace current occurrence button is clicked"""
        replaceText = self.replaceCombo.currentText()
        text = self.findtextCombo.currentText()
        isRegexp = self.regexpCheckBox.isChecked()
        isCase = self.caseCheckBox.isChecked()
        isWord = self.wordCheckBox.isChecked()
        searchAttributes = self._searchSupport.get(self._editorUUID)

        self.__updateReplaceHistory(text, replaceText)

        found = self._editor.findFirstTarget(text, isRegexp, isCase, isWord,
                                             searchAttributes.match[0],
                                             searchAttributes.match[1])
        if found:
            if self._editor.replaceTarget(str(replaceText)):
                GlobalData().mainWindow.showStatusBarMessage(
                    "1 occurrence replaced.")
                GlobalData().mainWindow.clearStatusBarMessage(1)
                # Positioning cursor to the end of the replaced text helps
                # to avoid problems of replacing 'text' with 'prefix_text'
                searchAttributes.match[1] += len(replaceText)
                self._editor.cursorPosition = searchAttributes.match[0], \
                                              searchAttributes.match[1]
                self.replaceButton.setEnabled(False)
                self.replaceAndMoveButton.setEnabled(False)
            else:
                GlobalData().mainWindow.showStatusBarMessage(
                    "No occurrences replaced.")
            # This will prevent highlighting the improper editor positions
            searchAttributes.match = [-1, -1, -1]

    def __onReplaceAndMove(self):
        """Triggered when replace-and-move button is clicked"""
        buttonFocused = self.replaceAndMoveButton.hasFocus()
        self.__onReplace()
        self.onNext(False)

        if buttonFocused:
            self.replaceAndMoveButton.setFocus()

    def __updateReplaceHistory(self, text, replaceText):
        """Updates the history in the project and in the combo boxes"""
        changedWhat = self._addToHistory(self.findtextCombo,
                                         self.findHistory, text)
        changedReplace = self._addToHistory(self.replaceCombo,
                                            self.replaceHistory, replaceText)
        if changedWhat or changedReplace:
            prj = GlobalData().project
            prj.setReplaceHistory(self.findHistory, self.replaceHistory)

    def onNext(self, clearSBMessage=True):
        """Triggered when the find next button is clicked"""
        oldLine = self._currentWidget.getLine()
        oldPos = self._currentWidget.getPos()
        FindReplaceBase.onNext(self, clearSBMessage)
        if oldLine == self._currentWidget.getLine() and \
           oldPos == self._currentWidget.getPos():
            FindReplaceBase.onNext(self, clearSBMessage)

        self.__updateReplaceHistory(self.findtextCombo.currentText(),
                                    self.replaceCombo.currentText())

    def onPrev(self):
        """Triggered when the find previous button is clicked"""
        FindReplaceBase.onPrev(self)
        self.__updateReplaceHistory(self.findtextCombo.currentText(),
                                    self.replaceCombo.currentText())
