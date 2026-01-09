import sys
import time
import pandas as pd
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, 
    QStackedWidget, QLabel, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QInputDialog

import mervis_state
import mervis_bigquery
import kis_chart
import kis_websocket 
import notification

from ui_widgets.chart_view import RealTimeChartWidget
from ui_widgets.chat_view import MervisChatWindow
from ui_widgets.stock_view import StockListWidget

class ChartLoader(QThread):
    data_loaded = pyqtSignal(object, object)
    error_occurred = pyqtSignal(str)

    def __init__(self, ticker):
        super().__init__()
        self.ticker = ticker

    def run(self):
        try:
            # kis_chart.get_daily_chart는 리스트를 반환함 (period 인자 제거)
            raw_data = kis_chart.get_daily_chart(self.ticker)
            
            if not raw_data:
                self.error_occurred.emit(f"{self.ticker} 데이터 로드 실패 (Empty)")
                return

            df = pd.DataFrame(raw_data)

            # API 키값 -> mplfinance 포맷 변환
            rename_map = {
                'open': 'Open', 'high': 'High', 'low': 'Low', 
                'clos': 'Close', 'last': 'Close',
                'acml_vol': 'Volume', 'vol': 'Volume',
                'xymd': 'Date', 'date': 'Date'
            }
            df.rename(columns=rename_map, inplace=True)

            # 숫자 변환
            cols = ['Open', 'High', 'Low', 'Close', 'Volume']
            for c in cols:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors='coerce')
            
            # 날짜 인덱스 설정
            if 'Date' in df.columns:
                df['Date'] = pd.to_datetime(df['Date'], format='%Y%m%d', errors='coerce')
                df.set_index('Date', inplace=True)
                df.sort_index(inplace=True)

            self.data_loaded.emit(self.ticker, df)

        except Exception as e:
            self.error_occurred.emit(f"차트 처리 오류: {str(e)}")

class WebSocketWorker(QThread):
    price_updated = pyqtSignal(str, float, float, float)

    def __init__(self):
        super().__init__()
        self.is_running = True

    def run(self):
        while self.is_running:
            try:
                active_tickers = mervis_state.get_all_realtime_tickers()
                
                for ticker in active_tickers:
                    data = mervis_state.get_realtime_data(ticker)
                    if not data: continue
                    
                    price = data.get('price', 0.0)
                    change = data.get('change', 0.0)
                    volume = data.get('volume', 0.0)
                    
                    self.price_updated.emit(ticker, price, change, volume)
                    
                time.sleep(0.5)
            except Exception as e:
                print(f"Worker Error: {e}")
                time.sleep(1)

    def stop(self):
        self.is_running = False

class MervisMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MERVIS")
        self.setGeometry(100, 100, 1300, 800)
        self.setStyleSheet("background-color: #F0F8FF;")

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.status_bar = QLabel(" 시스템 대기 중...")
        self.status_bar.setStyleSheet("background-color: #34495E; color: #ECF0F1; padding: 5px; font-size: 9pt;")
        main_layout.addWidget(self.status_bar)

        self.content_stack = QStackedWidget()
        main_layout.addWidget(self.content_stack)

        self.chart_view = RealTimeChartWidget()
        self.content_stack.addWidget(self.chart_view)

        self.stock_view = StockListWidget()
        self.content_stack.addWidget(self.stock_view)
        
        self.content_stack.setCurrentIndex(1)

        self.stock_view.request_chart_switch.connect(self.switch_to_chart_mode)
        self.stock_view.request_subscribe.connect(self.subscribe_ticker_from_list)

        self.ws_worker = WebSocketWorker()
        self.ws_worker.price_updated.connect(self.on_realtime_data_received)
        self.ws_worker.start()

    def subscribe_ticker_from_list(self, ticker):
        try:
            kis_websocket.add_watch_condition(ticker, 0, "MONITOR", "LIST_VIEW")
            self.status_bar.setText(f" [System] '{ticker}' 실시간 감시 시작")
        except Exception as e:
            print(f" [Error] 구독 요청 실패: {e}")

    def switch_to_chart_mode(self, ticker):
        self.content_stack.setCurrentIndex(0) 
        self.status_bar.setText(f" [Data] '{ticker}' 차트 데이터 로딩 중...")
        
        self.chart_loader = ChartLoader(ticker)
        self.chart_loader.data_loaded.connect(self.on_chart_loaded)
        self.chart_loader.error_occurred.connect(self.on_chart_error)
        self.chart_loader.start()
        
        kis_websocket.add_watch_condition(ticker, 0, "MONITOR", "CHART_VIEW")

    def on_chart_loaded(self, ticker, df):
        self.status_bar.setText(f" [Data] '{ticker}' 차트 로드 완료.")
        self.chart_view.load_data(ticker, df)

    def on_chart_error(self, msg):
        self.status_bar.setText(f" [Error] {msg}")
        QMessageBox.warning(self, "데이터 로드 실패", f"차트 데이터를 불러오지 못했습니다.\n{msg}")
        self.content_stack.setCurrentIndex(1)

    def on_realtime_data_received(self, ticker, price, change, volume):
        self.stock_view.update_prices(ticker, price, change)
        
        if self.content_stack.currentIndex() == 0:
            if self.chart_view.current_ticker == ticker:
                self.chart_view.update_realtime_price(price)
                self.status_bar.setText(f" [Live] {ticker}: ${price:,.2f} ({change:+.2f}%)")

    def closeEvent(self, event):
        self.ws_worker.stop()
        self.ws_worker.wait()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Malgun Gothic", 10))
    
    # 부팅 시 모드 선택 팝업 띄우기
    modes = ["1. 실전 투자 (REAL)", "2. 모의 투자 (MOCK)"]
    item, ok = QInputDialog.getItem(None, "모드 선택", "시스템 실행 모드를 선택하세요:", modes, 0, False)
    
    if ok and "REAL" in item:
        mervis_state.set_mode("REAL")
        print(" [System] 실전 투자 모드로 시작합니다.")
    else:
        mervis_state.set_mode("MOCK")
        print(" [System] 모의 투자 모드로 시작합니다.")

    # 웹소켓 백그라운드 시작
    kis_websocket.start_background_monitoring([])
    
    win = MervisMainWindow()
    
    # 채팅창 실행
    chat = MervisChatWindow()
    chat.show()
    
    win.show()
    sys.exit(app.exec())