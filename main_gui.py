import sys
import time
import pandas as pd
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QPushButton,
    QStackedWidget, QLabel, QMessageBox, QInputDialog, 
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QGroupBox, QFormLayout, QLineEdit, QComboBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor

import mervis_state
import mervis_bigquery
import kis_chart
import kis_websocket 
import kis_account
import notification
import mervis_examiner
import update_volume_tier
import mervis_ai 

from ui_widgets.chart_view import RealTimeChartWidget
from ui_widgets.chat_view import MervisChatWindow
from ui_widgets.stock_view import StockListWidget

class UserConfigWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(50, 50, 50, 50)
        title = QLabel("사용자 매매 설정 (MY)")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #2C3E50; margin-bottom: 20px;")
        layout.addWidget(title)
        
        form_group = QGroupBox("기본 매매 목표 설정")
        form_group.setStyleSheet("font-size: 14px; font-weight: bold;")
        form_layout = QFormLayout()
        form_layout.setSpacing(15)
        
        self.input_profit = QLineEdit()
        self.input_profit.setPlaceholderText("예: 5.0")
        self.input_loss = QLineEdit()
        self.input_loss.setPlaceholderText("예: -3.0")
        self.combo_tendency = QComboBox()
        self.combo_tendency.addItems(["공격형 (Scalping)", "중립형 (Swing)", "방어형 (Value Investing)"])

        form_layout.addRow("익절 목표 (%):", self.input_profit)
        form_layout.addRow("손절 제한 (%):", self.input_loss)
        form_layout.addRow("투자 성향:", self.combo_tendency)
        form_group.setLayout(form_layout)
        layout.addWidget(form_group)
        
        save_btn = QPushButton("설정 저장")
        save_btn.setFixedHeight(45)
        save_btn.setStyleSheet("background-color: #27AE60; color: white; font-weight: bold; font-size: 14px; border-radius: 5px;")
        save_btn.clicked.connect(self.save_config)
        layout.addWidget(save_btn)
        layout.addStretch()

    def save_config(self):
        QMessageBox.information(self, "저장 완료", "설정이 저장되었습니다.")

class SystemInitWorker(QThread):
    progress_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)

    def run(self):
        try:
            self.progress_signal.emit("데이터베이스 점검 중...")
            if not mervis_bigquery.check_db_freshness():
                self.progress_signal.emit("데이터 갱신 중...")
                update_volume_tier.update_volume_data()
            self.progress_signal.emit("매매 복기 중...")
            mervis_examiner.run_examination()
            self.progress_signal.emit("자산 기록 중...")
            my_asset = kis_account.get_my_total_assets()
            if my_asset:
                mervis_bigquery.save_daily_balance(
                    total_asset=my_asset['total'],
                    cash=my_asset['cash'],
                    stock_val=my_asset['stock'],
                    pnl_daily=my_asset['pnl']
                )
            self.finished_signal.emit(True, "초기화 완료")
        except Exception as e:
            self.finished_signal.emit(False, str(e))

class ChartLoader(QThread):
    # Signal에 AI 예측 데이터(prediction_info) 전달용 인자 추가
    data_loaded = pyqtSignal(object, object, float, object) 
    error_occurred = pyqtSignal(str)

    def __init__(self, ticker):
        super().__init__()
        self.ticker = ticker

    def run(self):
        try:
            raw_data = kis_chart.get_daily_chart(self.ticker)
            if not raw_data:
                self.error_occurred.emit(f"{self.ticker} 데이터 없음")
                return

            df = pd.DataFrame(raw_data)
            
            rename_map = {
                'clos': 'Close', 'last': 'Close',
                'open': 'Open', 
                'high': 'High', 
                'low': 'Low', 
                'acml_vol': 'Volume', 'vol': 'Volume', 'tvol': 'Volume',
                'xymd': 'Date', 'date': 'Date'
            }
            df.rename(columns=rename_map, inplace=True)

            if 'Volume' not in df.columns: df['Volume'] = 0
            
            cols = ['Open', 'High', 'Low', 'Close', 'Volume']
            for c in cols:
                if c in df.columns: 
                    df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
            
            if 'Date' in df.columns:
                df['Date'] = pd.to_datetime(df['Date'], format='%Y%m%d', errors='coerce')
                df.set_index('Date', inplace=True)
                df.index.name = 'Date' 
                df.sort_index(inplace=True) 
            else:
                self.error_occurred.emit("날짜 데이터(Date) 없음")
                return

            change_rate = 0.0
            if len(df) >= 2:
                prev = df['Close'].iloc[-2]
                curr = df['Close'].iloc[-1]
                if prev > 0:
                    change_rate = ((curr - prev) / prev) * 100

            # 빅쿼리 서버에서 AI 예측 데이터 가져오기
            prediction_info = mervis_bigquery.get_prediction(self.ticker)

            # 결과 전송 (예측 데이터 포함)
            self.data_loaded.emit(self.ticker, df, change_rate, prediction_info)

        except Exception as e:
            self.error_occurred.emit(f"차트 오류: {str(e)}")

class WebSocketWorker(QThread):
    price_updated = pyqtSignal(str, float, float, float)
    def __init__(self):
        super().__init__()
        self.is_running = True
    def run(self):
        while self.is_running:
            try:
                active = mervis_state.get_all_realtime_tickers()
                for ticker in active:
                    data = mervis_state.get_realtime_data(ticker)
                    if data:
                        self.price_updated.emit(ticker, data.get('price', 0.0), data.get('change', 0.0), data.get('volume', 0.0))
                time.sleep(0.5)
            except: time.sleep(1)
    def stop(self): self.is_running = False

class ChatWorker(QThread):
    response_received = pyqtSignal(str)
    def __init__(self, ai_engine, user_text):
        super().__init__()
        self.ai_engine = ai_engine
        self.user_text = user_text
    def run(self):
        try:
            resp = self.ai_engine.get_response(self.user_text)
            self.response_received.emit(resp)
        except Exception as e:
            self.response_received.emit(f"Error: {e}")

class EmptyWidget(QWidget):
    def __init__(self, text):
        super().__init__()
        l = QLabel(text)
        l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout(self); layout.addWidget(l)

class AssetWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        title = QLabel("내 자산 현황")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #2C3E50;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        self.summary_frame = QFrame()
        self.summary_frame.setStyleSheet("QFrame { background-color: white; border: 1px solid #BDC3C7; border-radius: 10px; } QLabel { font-size: 16px; padding: 5px; }")
        sl = QVBoxLayout(self.summary_frame)
        self.lbl_total = QLabel("-"); sl.addWidget(self.lbl_total)
        self.lbl_cash = QLabel("-"); sl.addWidget(self.lbl_cash)
        self.lbl_stock = QLabel("-"); sl.addWidget(self.lbl_stock)
        self.lbl_pnl = QLabel("-"); sl.addWidget(self.lbl_pnl)
        layout.addWidget(self.summary_frame)

        self.holding_table = QTableWidget()
        self.holding_table.setColumnCount(5)
        self.holding_table.setHorizontalHeaderLabels(["종목", "수량", "평가금($)", "수익률", "손익($)"])
        self.holding_table.verticalHeader().setVisible(False)
        self.holding_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.holding_table.setStyleSheet("QTableWidget { background-color: white; gridline-color: #ECF0F1; border: 1px solid #BDC3C7; } QHeaderView::section { background-color: #34495E; color: white; padding: 8px; border: none; font-weight: bold; }")
        layout.addWidget(self.holding_table)
        
        btn = QPushButton("새로고침")
        btn.setFixedSize(120, 40)
        btn.setStyleSheet("QPushButton { background-color: #3498DB; color: white; font-weight: bold; border-radius: 5px; }")
        btn.clicked.connect(self.load_asset_data)
        bl = QHBoxLayout(); bl.addWidget(btn); bl.addStretch()
        layout.addLayout(bl)
        
        self.load_asset_data()

    def load_asset_data(self):
        try:
            asset = kis_account.get_my_total_assets()
            if not asset:
                self.lbl_total.setText("자산 정보 로드 실패")
                return

            total = asset.get('total', 0)
            pnl = asset.get('pnl', 0.0)
            self.lbl_total.setText(f"총 자산: ${total:,.2f}")
            self.lbl_cash.setText(f"예수금: ${asset.get('cash', 0):,.2f}")
            self.lbl_stock.setText(f"주식 평가금: ${asset.get('stock', 0):,.2f}")
            
            color = "red" if pnl > 0 else "blue" if pnl < 0 else "black"
            self.lbl_pnl.setText(f"총 수익률: <span style='color:{color}'>{pnl:+.2f}%</span>")

            holdings = asset.get('holdings', [])
            self.holding_table.setRowCount(0)
            
            for h in holdings:
                row = self.holding_table.rowCount()
                self.holding_table.insertRow(row)
                self.holding_table.setItem(row, 0, QTableWidgetItem(str(h['code'])))
                self.holding_table.setItem(row, 1, QTableWidgetItem(f"{h['qty']:,}"))
                self.holding_table.setItem(row, 2, QTableWidgetItem(f"${h['val']:,.2f}"))
                
                rate_item = QTableWidgetItem(f"{h['pnl']:+.2f}%")
                rate_item.setForeground(QColor("red") if h['pnl'] > 0 else QColor("blue") if h['pnl'] < 0 else QColor("black"))
                self.holding_table.setItem(row, 3, rate_item)
                
                amt_item = QTableWidgetItem(f"${h['pnl_amt']:,.2f}")
                amt_item.setForeground(QColor("red") if h['pnl_amt'] > 0 else QColor("blue") if h['pnl_amt'] < 0 else QColor("black"))
                self.holding_table.setItem(row, 4, amt_item)
        except Exception as e:
            self.lbl_total.setText(f"오류: {e}")

class MervisMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MERVIS - Professional Trader")
        self.setGeometry(100, 100, 1300, 800)
        self.setStyleSheet("background-color: #F0F8FF;")

        self.ai_engine = mervis_ai.MervisAI_Engine()
        self.chat_worker = None
        self.chat_window = None
        
        self.current_selected_ticker = None
        self.current_prediction = None # 현재 AI 예측값 저장

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.create_top_menu(main_layout)

        self.status_bar = QLabel(" 시스템 대기 중...")
        self.status_bar.setStyleSheet("background-color: #34495E; color: #ECF0F1; padding: 5px; font-size: 9pt;")
        main_layout.addWidget(self.status_bar)

        self.content_stack = QStackedWidget()
        main_layout.addWidget(self.content_stack)

        self.stock_view = StockListWidget()
        self.content_stack.addWidget(self.stock_view)
        
        self.chart_view = RealTimeChartWidget()
        self.content_stack.addWidget(self.chart_view)

        self.asset_view = AssetWidget()
        self.content_stack.addWidget(self.asset_view)

        self.indicator_view = EmptyWidget("보조지표 설정 (준비 중)")
        self.content_stack.addWidget(self.indicator_view)

        self.settings_view = EmptyWidget("시스템 설정 (준비 중)")
        self.content_stack.addWidget(self.settings_view)

        self.user_config_view = UserConfigWidget()
        self.content_stack.addWidget(self.user_config_view)
        
        self.content_stack.setCurrentIndex(0)

        self.stock_view.request_chart_switch.connect(self.switch_to_chart_mode)
        self.stock_view.request_subscribe.connect(self.subscribe_ticker_from_list)
        self.stock_view.request_unsubscribe.connect(self.unsubscribe_ticker)

        self.ws_worker = WebSocketWorker()
        self.ws_worker.price_updated.connect(self.on_realtime_data_received)
        self.ws_worker.start()

        self.start_system_initialization()

    def create_top_menu(self, layout):
        menu_frame = QFrame()
        menu_frame.setFixedHeight(50)
        # 메뉴바
        menu_frame.setStyleSheet("""
            QFrame { background-color: #2C3E50; border-bottom: 2px solid #34495E; }
            QPushButton { 
                background-color: transparent; 
                color: #ECF0F1; 
                font-size: 14px; 
                font-weight: bold; 
                border: none; 
                padding: 10px 20px; 
            }
            QPushButton:hover { background-color: #34495E; color: #3498DB; }
            QPushButton:checked { color: #3498DB; border-bottom: 2px solid #3498DB; }
            #chat_btn { background-color: #27AE60; border-radius: 5px; margin: 5px; }
            #chat_btn:hover { background-color: #2ECC71; }
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
        btn_user = QPushButton("MY") 

        btn_stock.clicked.connect(lambda: self.content_stack.setCurrentIndex(0))
        btn_chart.clicked.connect(lambda: self.content_stack.setCurrentIndex(1))
        btn_asset.clicked.connect(self.switch_to_asset_view)
        btn_indi.clicked.connect(lambda: self.content_stack.setCurrentIndex(3))
        btn_conf.clicked.connect(lambda: self.content_stack.setCurrentIndex(4))
        btn_user.clicked.connect(lambda: self.content_stack.setCurrentIndex(5))

        btn_chat = QPushButton("채팅")
        btn_chat.setObjectName("chat_btn")
        btn_chat.clicked.connect(self.toggle_chat_window)

        menu_layout.addWidget(btn_stock)
        menu_layout.addWidget(btn_chart)
        menu_layout.addWidget(btn_asset)
        menu_layout.addWidget(btn_indi)
        menu_layout.addWidget(btn_conf)
        menu_layout.addWidget(btn_user)
        
        menu_layout.addStretch() 
        menu_layout.addWidget(btn_chat)

        layout.addWidget(menu_frame)

    def switch_to_asset_view(self):
        self.content_stack.setCurrentIndex(2)
        self.asset_view.load_asset_data()

    def toggle_chat_window(self):
        if self.chat_window is None:
            self.chat_window = MervisChatWindow()
            self.chat_window.message_sent.connect(self.handle_chat_message)
            self.chat_window.show()
        else:
            if self.chat_window.isVisible():
                self.chat_window.hide()
            else:
                self.chat_window.show()
                self.chat_window.raise_()
                self.chat_window.activateWindow()

    def handle_chat_message(self, text):
        self.chat_worker = ChatWorker(self.ai_engine, text)
        self.chat_worker.response_received.connect(self.on_chat_response)
        self.chat_worker.start()

    def on_chat_response(self, response):
        if self.chat_window:
            self.chat_window.append_bot_message(response)

    def start_system_initialization(self):
        self.status_bar.setText(" [System] 초기화 및 데이터 갱신 중...")
        self.init_worker = SystemInitWorker()
        self.init_worker.progress_signal.connect(lambda msg: self.status_bar.setText(f" [Init] {msg}"))
        self.init_worker.finished_signal.connect(self.on_init_finished)
        self.init_worker.start()

    def on_init_finished(self, success, msg):
        if success:
            self.status_bar.setText(f" [System] {msg}")
            self.asset_view.load_asset_data()
        else:
            self.status_bar.setText(f" [Error] {msg}")
            QMessageBox.warning(self, "초기화 오류", msg)

    def subscribe_ticker_from_list(self, ticker):
        try:
            kis_websocket.add_watch_condition(ticker, 0, "MONITOR", "LIST_VIEW")
            self.status_bar.setText(f" [System] '{ticker}' 실시간 감시 시작")
        except Exception as e:
            print(f" [Error] 구독 요청 실패: {e}")

    def unsubscribe_ticker(self, ticker):
        try:
            kis_websocket.remove_watch_condition(ticker)
            self.status_bar.setText(f" [System] '{ticker}' 감시 해제")
        except Exception as e:
            print(f" [Error] 해제 요청 실패: {e}")

    def switch_to_chart_mode(self, ticker):
        self.content_stack.setCurrentIndex(1) 
        self.status_bar.setText(f" [Data] '{ticker}' 차트 및 AI 분석 로딩 중...")
        
        self.current_selected_ticker = ticker
        
        self.chart_loader = ChartLoader(ticker)
        self.chart_loader.data_loaded.connect(self.on_chart_loaded)
        self.chart_loader.error_occurred.connect(self.on_chart_error)
        self.chart_loader.start()
        
        kis_websocket.add_watch_condition(ticker, 0, "MONITOR", "CHART_VIEW")

    def on_chart_loaded(self, ticker, df, change_rate, prediction_info):
        if ticker != self.current_selected_ticker: return

        # AI 예측 정보 저장
        self.current_prediction = prediction_info

        # 상태 표시줄에 AI 예측 표시
        status_msg = f" [Data] '{ticker}' 로드 완료."
        if prediction_info:
            pred_return = prediction_info.get('predicted_return', 0.0)
            # 퍼센트로 변환
            pred_pct = pred_return * 100
            
            # 색상 태그를 쓰려면 QLabel이 HTML을 지원해야 함. 여기선 텍스트로 표현.
            trend = "상승" if pred_pct > 0 else "하락"
            status_msg += f" | AI 내일 예측: {trend} {pred_pct:+.2f}%"
        else:
            status_msg += " | AI 예측: 데이터 부족"

        self.status_bar.setText(status_msg)
        
        # 무조건 Chart 데이터(API)를 신뢰하여 로드
        self.chart_view.load_data(ticker, df, change_rate)

    def on_chart_error(self, msg):
        self.status_bar.setText(f" [Error] {msg}")
        QMessageBox.warning(self, "데이터 로드 실패", f"차트 데이터를 불러오지 못했습니다.\n{msg}")
        self.content_stack.setCurrentIndex(0)

    def on_realtime_data_received(self, ticker, price, change, volume):
        self.stock_view.update_prices(ticker, price, change)
        
        if self.content_stack.currentIndex() == 1:
            if self.chart_view.current_ticker == ticker:
                self.chart_view.update_realtime_price(price)
                self.chart_view.update_header_info(price, change)
                
                # 실시간 정보와 AI 정보 함께 표시
                base_msg = f" [Live] {ticker}: ${price:,.2f} ({change:+.2f}%)"
                if self.current_prediction:
                    pred_pct = self.current_prediction.get('predicted_return', 0.0) * 100
                    base_msg += f" | AI: {pred_pct:+.2f}%"
                
                self.status_bar.setText(base_msg)

    def closeEvent(self, event):
        if self.chat_window:
            self.chat_window.close()
        self.ws_worker.stop()
        self.ws_worker.wait()
        kis_websocket.stop_monitoring()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Malgun Gothic", 10))
    
    modes = ["1. 실전 투자 (REAL)", "2. 모의 투자 (MOCK)"]
    item, ok = QInputDialog.getItem(None, "모드 선택", "시스템 실행 모드를 선택하세요:", modes, 0, False)
    
    if ok and "REAL" in item:
        mervis_state.set_mode("REAL")
        print(" [System] 실전 투자 모드로 시작합니다.")
    else:
        mervis_state.set_mode("MOCK")
        print(" [System] 모의 투자 모드로 시작합니다.")

    kis_websocket.start_background_monitoring([])
    
    win = MervisMainWindow()
    win.show()
    
    sys.exit(app.exec())