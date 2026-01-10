import sys
import json
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, 
    QHeaderView, QAbstractItemView, QLineEdit, QMessageBox, QCompleter, QPushButton
)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QColor

import mervis_bigquery
import kis_chart

class UniverseLoader(QThread):
    loaded = pyqtSignal(list)

    def run(self):
        tickers = mervis_bigquery.get_all_tickers_simple()
        self.loaded.emit(tickers)

class StockListWidget(QWidget):
    request_chart_switch = pyqtSignal(str) 
    request_subscribe = pyqtSignal(str)
    request_unsubscribe = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(20, 20, 20, 20)
        self.layout.setSpacing(15)

        # 1. 검색바
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("데이터 로딩 중...") 
        self.search_bar.setEnabled(False)
        self.search_bar.returnPressed.connect(self.on_enter_pressed) # 엔터키 연결
        
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

        # 2. 관심 종목 테이블
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
        
        self.stock_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.stock_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.stock_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.stock_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.stock_table.setColumnWidth(3, 80)

        self.layout.addWidget(self.stock_table)

        self.saved_tickers = []
        self.data_file = "watched_tickers.json"
        
        # 저장된 종목 로드
        self.load_saved_tickers()
        
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

    def on_enter_pressed(self):
        text = self.search_bar.text().strip().upper()
        if not text: return
        self.process_add_ticker(text)

    def on_ticker_selected(self, text):
        self.process_add_ticker(text.upper())

    def process_add_ticker(self, ticker):
        if ticker in self.saved_tickers:
            QMessageBox.information(self, "알림", f"'{ticker}' 종목은 이미 목록에 있습니다.")
            self.search_bar.clear()
            return
        
        # 검색바 엔터/선택 시 팝업 없이 바로 추가
        self.add_stock_to_list(ticker)
        self.search_bar.clear()

    def add_stock_to_list(self, ticker):
        row = self.stock_table.rowCount()
        self.stock_table.insertRow(row)
        
        self.stock_table.setItem(row, 0, QTableWidgetItem(ticker))
        self.stock_table.setItem(row, 1, QTableWidgetItem("..."))
        self.stock_table.setItem(row, 2, QTableWidgetItem("-"))
        
        # 삭제 버튼
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
        del_btn.clicked.connect(lambda _, t=ticker: self.delete_stock(t))
        self.stock_table.setCellWidget(row, 3, del_btn)
        
        if ticker not in self.saved_tickers:
            self.saved_tickers.append(ticker)
            self.save_tickers_to_file()

        # 초기 데이터 즉시 조회
        self.fetch_initial_price(ticker, row)

        self.request_subscribe.emit(ticker)

    def fetch_initial_price(self, ticker, row):
        # 웹소켓 대기 시간 해소를 위해 API로 1회 조회
        try:
            data = kis_chart.get_daily_chart(ticker)
            if data:
                last_candle = data[-1]
                price = float(last_candle.get('clos') or last_candle.get('last') or 0)
                
                rate = 0.0
                if len(data) >= 2:
                    prev = float(data[-2].get('clos') or data[-2].get('last') or 0)
                    if prev > 0:
                        rate = ((price - prev) / prev) * 100
                
                self.stock_table.setItem(row, 1, QTableWidgetItem(f"${price:.2f}"))
                
                rate_item = QTableWidgetItem(f"{rate:+.2f}%")
                color = QColor("red") if rate > 0 else (QColor("blue") if rate < 0 else QColor("black"))
                rate_item.setForeground(color)
                self.stock_table.setItem(row, 2, rate_item)
        except:
            pass

    def delete_stock(self, ticker):
        reply = QMessageBox.question(
            self,
            "종목 삭제",
            f"'{ticker}' 삭제하시겠습니까?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            target_row = -1
            for r in range(self.stock_table.rowCount()):
                if self.stock_table.item(r, 0).text() == ticker:
                    target_row = r
                    break
            
            if target_row != -1:
                self.stock_table.removeRow(target_row)
                if ticker in self.saved_tickers:
                    self.saved_tickers.remove(ticker)
                    self.save_tickers_to_file()
                
                self.request_unsubscribe.emit(ticker)

    def save_tickers_to_file(self):
        try:
            with open(self.data_file, 'w') as f:
                json.dump(self.saved_tickers, f)
        except Exception as e:
            print(f"저장 실패: {e}")

    def load_saved_tickers(self):
        if not os.path.exists(self.data_file): return
        try:
            with open(self.data_file, 'r') as f:
                tickers = json.load(f)
                for t in tickers:
                    self.add_stock_to_list(t)
        except Exception as e:
            print(f"로드 실패: {e}")

    def on_table_double_clicked(self, row, col):
        if col == 3: return
        item = self.stock_table.item(row, 0)
        if item:
            ticker = item.text()
            self.request_chart_switch.emit(ticker)

    def update_prices(self, ticker, price, rate):
        for r in range(self.stock_table.rowCount()):
            if self.stock_table.item(r, 0).text() == ticker:
                self.stock_table.setItem(r, 1, QTableWidgetItem(f"${price:.2f}"))
                
                rate_item = QTableWidgetItem(f"{rate:+.2f}%")
                if rate > 0: rate_item.setForeground(QColor("red"))
                elif rate < 0: rate_item.setForeground(QColor("blue"))
                else: rate_item.setForeground(QColor("black"))
                
                self.stock_table.setItem(r, 2, rate_item)
                break