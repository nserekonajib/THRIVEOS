# utils/receipt_printer.py
from escpos.printer import Network, Usb
from escpos.constants import PAPER_FULL_CUT, PAPER_PART_CUT
import os
from config import Config

class ReceiptPrinter:
    def __init__(self):
        self.printer_type = Config.PRINTER_TYPE  # 'network' or 'usb'
        self.printer_ip = Config.PRINTER_IP
        self.printer_port = Config.PRINTER_PORT
        self.printer_vendor_id = Config.PRINTER_VENDOR_ID
        self.printer_product_id = Config.PRINTER_PRODUCT_ID
        self.printer = None
        
    def connect(self):
        """Connect to printer"""
        try:
            if self.printer_type == 'network':
                self.printer = Network(self.printer_ip, port=self.printer_port)
            elif self.printer_type == 'usb':
                self.printer = Usb(self.printer_vendor_id, self.printer_product_id)
            else:
                raise ValueError(f"Unknown printer type: {self.printer_type}")
            
            return True
        except Exception as e:
            print(f"Printer connection error: {e}")
            return False
    
    def print_receipt(self, receipt_data):
        """Print receipt"""
        if not self.connect():
            return False
        
        try:
            printer = self.printer
            
            # Header
            printer.set(align='center', width=2, height=2)
            printer.textln("=" * 32)
            printer.textln(receipt_data['business']['business_name'])
            printer.textln("=" * 32)
            
            printer.set(align='left', width=1, height=1)
            printer.textln(f"Date: {receipt_data['sale']['date']}")
            printer.textln(f"Receipt: {receipt_data['sale']['reference']}")
            printer.textln(f"Cashier: {receipt_data['cashier']}")
            printer.textln(f"Customer: {receipt_data['sale']['customer_name']}")
            if receipt_data['sale']['customer_phone']:
                printer.textln(f"Phone: {receipt_data['sale']['customer_phone']}")
            
            printer.textln("-" * 32)
            
            # Items
            for item in receipt_data['items']:
                product_name = item['products']['name']
                if len(product_name) > 20:
                    product_name = product_name[:20]
                
                qty = item['quantity']
                price = item['unit_price']
                total = item['total_price']
                
                printer.textln(f"{product_name:<20} {qty:>3} {total:>7.2f}")
                printer.textln(f"{' ':<20} @{price:.2f}")
            
            printer.textln("-" * 32)
            
            # Totals
            printer.textln(f"{'Subtotal:':<25} {receipt_data['sale']['subtotal']:>7.2f}")
            if receipt_data['sale']['discount'] > 0:
                printer.textln(f"{'Discount:':<25} -{receipt_data['sale']['discount']:>7.2f}")
            if receipt_data['sale']['tax'] > 0:
                printer.textln(f"{'Tax:':<25} {receipt_data['sale']['tax']:>7.2f}")
            printer.textln(f"{'TOTAL:':<25} {receipt_data['sale']['total']:>7.2f}")
            
            printer.textln("-" * 32)
            printer.textln(f"Payment: {receipt_data['sale']['payment_method'].upper()}")
            printer.textln(f"Status: {receipt_data['sale']['payment_status'].upper()}")
            
            # Footer
            printer.set(align='center')
            printer.textln("=" * 32)
            printer.textln("THANK YOU FOR YOUR BUSINESS!")
            printer.textln("=" * 32)
            
            # Cut paper
            printer.cut()
            
            return True
            
        except Exception as e:
            print(f"Print error: {e}")
            return False
        finally:
            if self.printer:
                self.printer.close()