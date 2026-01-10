import sys
import time
import pandas as pd
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QPushButton,
    QStackedWidget, QLabel, QMessageBox, QInputDialog
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

# 모듈 임포트
import mervis_state
import mervis_bigquery
import kis_chart
import kis_websocket 
import kis_account
import notification

# UI 위젯 임포트
from ui_widgets.chart_view import RealTimeChartWidget
from ui_widgets.chat_view import MervisChatWindow
from ui_widgets.stock_view import StockListWidget

class ChartLoader(QThread):
    data_loaded = pyqtSignal(object, object, float)
    error_occurred = pyqtSignal(str)

    def __init__(self, ticker):
        super().__init__()
        self.ticker = ticker

    def run(self):
        try:
            # kis_chart 모듈을 통해 일봉 데이터 조회
            raw_data = kis_chart.get_daily_chart(self.ticker)
            
            if not raw_data:
                self.error_occurred.emit(f"{self.ticker} 데이터 로드 실패 (Empty)")
                return

            df = pd.DataFrame(raw_data)

            # API 응답 키 매핑
            rename_map = {
                'open': 'Open', 'high': 'High', 'low': 'Low', 
                'clos': 'Close', 'last': 'Close',
                'acml_vol': 'Volume', 'vol': 'Volume',
                'xymd': 'Date', 'date': 'Date'
            }
            df.rename(columns=rename_map, inplace=True)

            # 수치형 변환
            cols = ['Open', 'High', 'Low', 'Close', 'Volume']
            for c in cols:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors='coerce')
            
            # 인덱스 설정
            if 'Date' in df.columns:
                df['Date'] = pd.to_datetime(df['Date'], format='%Y%m%d', errors='coerce')
                df.set_index('Date', inplace=True)
                df.sort_index(inplace=True)

            # 전일 대비 등락률 계산
            change_rate = 0.0
            if len(df) >= 2:
                prev_close = df['Close'].iloc[-2]
                curr_close = df['Close'].iloc[-1]
                if prev_close > 0:
                    change_rate = ((curr_close - prev_close) / prev_close) * 100

            self.data_loaded.emit(self.ticker, df, change_rate)

        except Exception as e:
            self.error_occurred.emit(f"차트 처리 오류: {str(e)}")

class WebSocketWorker(QThread):
    price_updated = pyqtSignal(str, float, float, float)

    def __init__(self):
        super().__init__()
        self.is_running = True

    def run(self):
        # mervis_state를 주기적으로 조회하여 GUI 업데이트 신호 발송
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

class EmptyWidget(QWidget):
    def __init__(self, text):
        super().__init__()
        layout = QVBoxLayout(self)
        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("font-size: 20px; color: gray; font-weight: bold;")
        layout.addWidget(label)

class AssetWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(50, 50, 50, 50)
        
        title = QLabel("내 자산 현황")
        title.setStyleSheet("font-size: 24px; font-weight: bold; margin-bottom: 20px; color: #2C3E50;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self.info_label = QLabel("데이터 로딩 중...")
        self.info_label.setStyleSheet("""
            background-color: white; 
            border: 2px solid #BDC3C7; 
            border-radius: 10px; 
            padding: 20px;
            font-size: 16px; 
            line-height: 1.6;
        """)
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.info_label)
        
        btn_layout = QHBoxLayout()
        refresh_btn = QPushButton("새로고침")
        refresh_btn.setFixedSize(120, 40)
        refresh_btn.setStyleSheet("background-color: #3498DB; color: white; font-weight: bold; border-radius: 5px;")
        refresh_btn.clicked.connect(self.load_asset_data)
        btn_layout.addWidget(refresh_btn)
        
        layout.addLayout(btn_layout)
        layout.addStretch()
        
        self.load_asset_data()

    def load_asset_data(self):
        try:
            asset = kis_account.get_my_total_assets()
            if not asset:
                self.info_label.setText("자산 정보를 불러올 수 없습니다.")
                return

            total = asset.get('total', 0)
            cash = asset.get('cash', 0)
            stock = asset.get('stock', 0)
            pnl = asset.get('pnl', 0.0)
            
            pnl_color = "red" if pnl > 0 else "blue" if pnl < 0 else "black"
            
            html_text = f"""
            <h3>총 자산 평가액: ${total:,.2f}</h3>
            <hr>
            <ul>
                <li><b>보유 현금:</b> ${cash:,.2f}</li>
                <li><b>주식 평가금:</b> ${stock:,.2f}</li>
                <li><b>금일 수익률:</b> <span style='color:{pnl_color}; font-weight:bold;'>{pnl:.2f}%</span></li>
            </ul>
            """
            self.info_label.setText(html_text)
            
        except Exception as e:
            self.info_label.setText(f"데이터 로드 오류: {e}")

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

        # 상단 메뉴바
        self.create_top_menu(main_layout)

        # 상태바
        self.status_bar = QLabel(" 시스템 대기 중...")
        self.status_bar.setStyleSheet("background-color: #34495E; color: #ECF0F1; padding: 5px; font-size: 9pt;")
        main_layout.addWidget(self.status_bar)

        # 스택 위젯
        self.content_stack = QStackedWidget()
        main_layout.addWidget(self.content_stack)

        # 화면 구성
        self.stock_view = StockListWidget()
        self.content_stack.addWidget(self.stock_view)     # 0: 관심 종목

        self.chart_view = RealTimeChartWidget()
        self.content_stack.addWidget(self.chart_view)     # 1: 차트

        self.asset_view = AssetWidget()                   # 2: 자산
        self.content_stack.addWidget(self.asset_view)

        self.indicator_view = EmptyWidget("보조지표 설정 (준비 중)") # 3: 보조지표
        self.content_stack.addWidget(self.indicator_view)

        self.settings_view = EmptyWidget("설정 화면 (준비 중)")      # 4: 설정
        self.content_stack.addWidget(self.settings_view)
        
        self.content_stack.setCurrentIndex(0)

        # 시그널 연결
        self.stock_view.request_chart_switch.connect(self.switch_to_chart_mode)
        self.stock_view.request_subscribe.connect(self.subscribe_ticker_from_list)
        self.stock_view.request_unsubscribe.connect(self.unsubscribe_ticker)

        # 웹소켓 상태 감지 워커 시작
        self.ws_worker = WebSocketWorker()
        self.ws_worker.price_updated.connect(self.on_realtime_data_received)
        self.ws_worker.start()

    def create_top_menu(self, layout):
        menu_frame = QFrame()
        menu_frame.setFixedHeight(50)
        menu_frame.setStyleSheet("""
            QFrame { background-color: #2C3E50; border-bottom: 2px solid #34495E; }
            QPushButton { background-color: transparent; color: #ECF0F1; font-size: 14px; font-weight: bold; border: none; padding: 10px 20px; }
            QPushButton:hover { background-color: #34495E; color: #3498DB; }
            QPushButton:checked { color: #3498DB; border-bottom: 2px solid #3498DB; }
        """)
        
        menu_layout = QHBoxLayout(menu_frame)
        menu_layout.setContentsMargins(10, 0, 10, 0)
        menu_layout.setSpacing(10)
        menu_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        btn_stock = QPushButton("관심 종목")
        btn_chart = QPushButton("차트")
        btn_asset = QPushButton("자산")
        btn_indi = QPushButton("보조지표")
        btn_conf = QPushButton("설정")

        btn_stock.clicked.connect(lambda: self.content_stack.setCurrentIndex(0))
        btn_chart.clicked.connect(lambda: self.content_stack.setCurrentIndex(1))
        btn_asset.clicked.connect(lambda: self.content_stack.setCurrentIndex(2))
        btn_indi.clicked.connect(lambda: self.content_stack.setCurrentIndex(3))
        btn_conf.clicked.connect(lambda: self.content_stack.setCurrentIndex(4))

        menu_layout.addWidget(btn_stock)
        menu_layout.addWidget(btn_chart)
        menu_layout.addWidget(btn_asset)
        menu_layout.addWidget(btn_indi)
        menu_layout.addWidget(btn_conf)

        layout.addWidget(menu_frame)

    def subscribe_ticker_from_list(self, ticker):
        try:
            # kis_websocket을 이용해 종목 구독 요청 (감시 조건 추가)
            kis_websocket.add_watch_condition(ticker, 0, "MONITOR", "LIST_VIEW")
            self.status_bar.setText(f" [System] '{ticker}' 실시간 감시 시작")
        except Exception as e:
            print(f" [Error] 구독 요청 실패: {e}")

    def unsubscribe_ticker(self, ticker):
        try:
            # kis_websocket을 이용해 구독 해제
            kis_websocket.remove_watch_condition(ticker)
            self.status_bar.setText(f" [System] '{ticker}' 감시 해제")
        except Exception as e:
            print(f" [Error] 해제 요청 실패: {e}")

    def switch_to_chart_mode(self, ticker):
        self.content_stack.setCurrentIndex(1) 
        self.status_bar.setText(f" [Data] '{ticker}' 차트 데이터 로딩 중...")
        
        self.chart_loader = ChartLoader(ticker)
        self.chart_loader.data_loaded.connect(self.on_chart_loaded)
        self.chart_loader.error_occurred.connect(self.on_chart_error)
        self.chart_loader.start()
        
        # 차트 진입 시에도 감시 요청
        kis_websocket.add_watch_condition(ticker, 0, "MONITOR", "CHART_VIEW")

    def on_chart_loaded(self, ticker, df, change_rate):
        self.status_bar.setText(f" [Data] '{ticker}' 차트 로드 완료.")
        self.chart_view.load_data(ticker, df, change_rate)

    def on_chart_error(self, msg):
        self.status_bar.setText(f" [Error] {msg}")
        QMessageBox.warning(self, "데이터 로드 실패", f"차트 데이터를 불러오지 못했습니다.\n{msg}")
        self.content_stack.setCurrentIndex(0)

    def on_realtime_data_received(self, ticker, price, change, volume):
        # 1. 종목 리스트 갱신
        self.stock_view.update_prices(ticker, price, change)
        
        # 2. 현재 보고 있는 차트 갱신
        if self.content_stack.currentIndex() == 1:
            if self.chart_view.current_ticker == ticker:
                self.chart_view.update_realtime_price(price)
                self.status_bar.setText(f" [Live] {ticker}: ${price:,.2f} ({change:+.2f}%)")

    def closeEvent(self, event):
        self.ws_worker.stop()
        self.ws_worker.wait()
        # 프로그램 종료 시 웹소켓 연결 정리
        kis_websocket.stop_monitoring()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Malgun Gothic", 10))
    
    # 모드 선택 팝업
    modes = ["1. 실전 투자 (REAL)", "2. 모의 투자 (MOCK)"]
    item, ok = QInputDialog.getItem(None, "모드 선택", "시스템 실행 모드를 선택하세요:", modes, 0, False)
    
    if ok and "REAL" in item:
        mervis_state.set_mode("REAL")
        print(" [System] 실전 투자 모드로 시작합니다.")
    else:
        mervis_state.set_mode("MOCK")
        print(" [System] 모의 투자 모드로 시작합니다.")

    # 웹소켓 모니터링 시작 (초기 빈 리스트)
    kis_websocket.start_background_monitoring([])
    
    win = MervisMainWindow()
    
    chat = MervisChatWindow()
    chat.show()
    
    win.show()
    sys.exit(app.exec())