# -*- coding: utf-8 -*-
#
# codimension - graphics python two-way code editor and analyzer
# Copyright (C) 2010-2020 Sergey Satskiy <sergey.satskiy@gmail.com>
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

"""Dependency diagram grphics items"""

from ui.qt import Qt, QPointF, QPen, QBrush, QGraphicsRectItem, QGraphicsItem
from flowui.cellelement import CellElement
from flowui.textmixin import TextMixin
from flowui.auxitems import BadgeItem


class SelfModule(CellElement, TextMixin, QGraphicsRectItem):

    """Represents the module for which the dependencies are drawn"""

    def __init__(self, fileName, needConnector, canvas, x, y):
        CellElement.__init__(self, None, canvas, x, y)
        TextMixin.__init__(self)
        QGraphicsRectItem.__init__(self, canvas.scopeRectangle)
        self.kind = CellElement.DEPS_SELF_MODULE
        self.fileName = fileName

        self.needConnector = needConnector
        self.connector = None

        # To make double click delivered
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)

    def render(self):
        """Renders the cell"""
        settings = self.canvas.settings
        text = os.path.basename(self.fileName).split('.')[0]
        self.setupText(self, customText=text)

        vPadding = 2 * (settings.vCellPadding + settings.vTextPadding)
        self.minHeight = self.textRect.height() + vPadding
        hPadding = 2 * (settings.hCellPadding + settings.hTextPadding)
        self.minWidth = max(self.textRect.width() + hPadding,
                            settings.minWidth)

        # Add badges
        self.aboveBadges.append(BadgeItem(self, 'doc'))
        self.aboveBadges.append(BadgeItem(self, 'path'))

        self.minHeight += self.aboveBadges.height + settings.badgeToScopeVPadding
        self.minWidth = max(self.aboveBadges.width + 2 * settings.hCellPadding,
                            self.minWidth)

        self.height = self.minHeight
        self.width = self.minWidth
        return (self.width, self.height)

    def draw(self, scene, baseX, baseY):
        """Draws the cell"""
        self.baseX = baseX
        self.baseY = baseY

        # Add the connector as a separate scene item to make the selection
        # working properly
        settings = self.canvas.settings
        self.connector = Connector(self.canvas, baseX + settings.mainLine,
                                   baseY,
                                   baseX + settings.mainLine,
                                   baseY + self.height)
        scene.addItem(self.connector)

        # Draw comment badges
        self.aboveBadges.draw(scene, settings, baseX, baseY, self.minWidth)
        takenByBadges = 0
        if self.aboveBadges.hasAny():
            takenByBadges = self.aboveBadges.height + settings.badgeToScopeVPadding

        # Setting the rectangle is important for the selection and for
        # redrawing. Thus the selection pen with must be considered too.
        xPos = baseX + settings.hCellPadding
        yPos = baseY + settings.vCellPadding
        penWidth = settings.selectPenWidth - 1
        self.setRect(
            xPos - penWidth, yPos - penWidth + takenByBadges,
            self.minWidth - 2 * settings.hCellPadding + 2 * penWidth,
            self.minHeight - 2 * settings.vCellPadding + 2 * penWidth - takenByBadges)
        scene.addItem(self)

    def paint(self, painter, option, widget):
        """Draws the code block"""
        del option      # unused argument
        del widget      # unused argument

        settings = self.canvas.settings
        painter.setPen(self.getPainterPen(self.isSelected(), self.borderColor))
        painter.setBrush(QBrush(self.bgColor))

        rectWidth = self.minWidth - 2 * settings.hCellPadding
        rectHeight = self.minHeight - 2 * settings.vCellPadding

        yPos = self.baseY + settings.vCellPadding
        if self.aboveBadges.hasAny():
            badgeShift = self.aboveBadges.height + settings.badgeToScopeVPadding
            yPos += badgeShift
            rectHeight -= badgeShift

        painter.drawRect(self.baseX + settings.hCellPadding,
                         yPos, rectWidth, rectHeight)

        # Draw the text in the rectangle
        pen = QPen(self.fgColor)
        painter.setFont(settings.monoFont)
        painter.setPen(pen)

        textWidth = self.textRect.width() + 2 * settings.hTextPadding
        textShift = (rectWidth - textWidth) / 2
        painter.drawText(
            self.baseX + settings.hCellPadding +
            settings.hTextPadding + textShift,
            yPos + settings.vTextPadding,
            self.textRect.width(), self.textRect.height(),
            Qt.AlignLeft, self.text)


