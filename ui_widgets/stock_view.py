import sys
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, 
    QHeaderView, QAbstractItemView, QLineEdit, QMessageBox, QCompleter, QPushButton
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QColor

import mervis_bigquery

class UniverseLoader(QThread):
    loaded = pyqtSignal(list)

    def run(self):
        tickers = mervis_bigquery.get_all_tickers_simple()
        self.loaded.emit(tickers)

class StockListWidget(QWidget):
    request_chart_switch = pyqtSignal(str) 
    request_subscribe = pyqtSignal(str)
    request_unsubscribe = pyqtSignal(str) # [신규] 구독 취소 시그널 추가

    def __init__(self):
        super().__init__()
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(15)

        # 1. 검색바
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("데이터 로딩 중...") 
        self.search_bar.setEnabled(False)
        self.search_bar.setStyleSheet("""
            QLineEdit {
                background-color: white;
                border: 2px solid #BDC3C7;
                border-radius: 5px;
                padding: 10px;
                font-size: 11pt;
                color: #2C3E50;
            }
            QLineEdit:focus {
                border: 2px solid #3498DB;
            }
            QLineEdit:disabled {
                background-color: #ECF0F1;
                color: #7F8C8D;
            }
        """)
        self.layout.addWidget(self.search_bar)

        # 2. 관심 종목 테이블 (삭제 버튼 열 추가로 컬럼 수 4개)
        self.stock_table = QTableWidget()
        self.stock_table.setColumnCount(4)
        self.stock_table.setHorizontalHeaderLabels(["종목명", "현재가", "등락률", "삭제"])
        self.stock_table.verticalHeader().setVisible(False)
        self.stock_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.stock_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.stock_table.setAlternatingRowColors(True)
        self.stock_table.cellDoubleClicked.connect(self.on_table_double_clicked)
        
        self.stock_table.setStyleSheet("""
            QTableWidget {
                background-color: white;
                gridline-color: #ECF0F1;
                border: 1px solid #BDC3C7;
                font-size: 11pt;
            }
            QHeaderView::section {
                background-color: #34495E;
                color: white;
                padding: 8px;
                border: none;
                font-weight: bold;
            }
            QTableWidget::item {
                padding: 5px;
            }
        """)
        # 컬럼 너비 설정
        self.stock_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.stock_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.stock_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.stock_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed) # 삭제 버튼 고정폭
        self.stock_table.setColumnWidth(3, 80) # 폭 80px

        self.layout.addWidget(self.stock_table)

        self.saved_tickers = []
        
        # 백그라운드 로딩 시작
        self.loader = UniverseLoader()
        self.loader.loaded.connect(self.init_search_completer)
        self.loader.start()

    def init_search_completer(self, ticker_list):
        if not ticker_list:
            self.search_bar.setPlaceholderText("DB 연결 실패 (종목 로드 불가)")
            return

        self.completer = QCompleter(ticker_list, self)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setFilterMode(Qt.MatchFlag.MatchStartsWith)
        self.search_bar.setCompleter(self.completer)
        
        self.completer.activated.connect(self.on_ticker_selected)
        
        self.search_bar.setEnabled(True)
        self.search_bar.setPlaceholderText(f"종목 ID로 검색 (총 {len(ticker_list)}개 로드됨)")

    def on_ticker_selected(self, text):
        ticker = text.upper()
        
        if ticker in self.saved_tickers:
            QMessageBox.information(self, "알림", f"'{ticker}' 종목은 이미 목록에 있습니다.")
            self.search_bar.clear()
            return

        reply = QMessageBox.question(
            self, 
            "종목 추가", 
            f"'{ticker}' 종목을 관심 목록에 추가하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.add_stock_to_list(ticker)
            
        self.search_bar.clear()

    def add_stock_to_list(self, ticker):
        row = self.stock_table.rowCount()
        self.stock_table.insertRow(row)
        
        self.stock_table.setItem(row, 0, QTableWidgetItem(ticker))
        self.stock_table.setItem(row, 1, QTableWidgetItem("-"))
        self.stock_table.setItem(row, 2, QTableWidgetItem("-"))
        
        # 삭제 버튼 추가
        del_btn = QPushButton("X")
        del_btn.setStyleSheet("""
            QPushButton {
                background-color: #E74C3C; 
                color: white; 
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #C0392B;
            }
        """)
        # 버튼 클릭 시 해당 종목 삭제 함수 호출 (람다로 ticker 전달)
        del_btn.clicked.connect(lambda _, t=ticker: self.delete_stock(t))
        self.stock_table.setCellWidget(row, 3, del_btn)
        
        self.saved_tickers.append(ticker)

        print(f" [UI] '{ticker}' 실시간 구독 요청 전송")
        self.request_subscribe.emit(ticker)

    def delete_stock(self, ticker):
        """종목 삭제 처리"""
        reply = QMessageBox.question(
            self,
            "종목 삭제",
            f"'{ticker}' 종목을 목록에서 삭제하시겠습니까?\n(실시간 감시도 중단됩니다)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            # 1. 테이블에서 행 찾기
            target_row = -1
            for r in range(self.stock_table.rowCount()):
                if self.stock_table.item(r, 0).text() == ticker:
                    target_row = r
                    break
            
            # 2. 행 삭제 및 리스트 제거
            if target_row != -1:
                self.stock_table.removeRow(target_row)
                if ticker in self.saved_tickers:
                    self.saved_tickers.remove(ticker)
                
                # 3. 구독 취소 시그널 전송
                self.request_unsubscribe.emit(ticker)
                print(f" [UI] '{ticker}' 삭제 완료 및 구독 취소 요청")

    def on_table_double_clicked(self, row, col):
        # 삭제 버튼 컬럼(3번) 클릭 시에는 차트 전환 막기 (버튼 이벤트가 우선이지만 안전장치)
        if col == 3: return
        
        item = self.stock_table.item(row, 0)
        if item:
            ticker = item.text()
            self.request_chart_switch.emit(ticker)

    def update_prices(self, ticker, price, rate):
        target_row = -1
        for r in range(self.stock_table.rowCount()):
            if self.stock_table.item(r, 0).text() == ticker:
                target_row = r
                break
        
        if target_row != -1:
            self.stock_table.setItem(target_row, 1, QTableWidgetItem(f"${price:.2f}"))
            
            rate_item = QTableWidgetItem(f"{rate:+.2f}%")
            if rate > 0: rate_item.setForeground(QColor("red"))
            elif rate < 0: rate_item.setForeground(QColor("blue"))
            else: rate_item.setForeground(QColor("black"))
            
            self.stock_table.setItem(target_row, 2, rate_item)