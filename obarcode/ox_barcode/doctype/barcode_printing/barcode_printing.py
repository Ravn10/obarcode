# -*- coding: utf-8 -*-
# Copyright (c) 2021, lxy and contributors
# For license information, please see license.txt

from __future__ import unicode_literals
from erpnext.e_commerce.doctype.e_commerce_settings.e_commerce_settings import get_shopping_cart_settings
from erpnext.utilities.product import get_price
import frappe, json, urllib
from frappe.model.document import Document
from frappe.model.mapper import get_mapped_doc
from frappe import msgprint, _
from frappe.utils.data import fmt_money
from six import string_types, iteritems
import qrcode, io, os
from io import BytesIO
import base64
from frappe.integrations.utils import make_get_request, make_post_request, create_request_log
from frappe.utils import cstr, flt, cint, nowdate, get_url
import requests
from PIL import Image
import json
import random
from PyPDF2 import PdfFileReader,PdfFileMerger
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.graphics.barcode import eanbc
from reportlab.graphics.shapes import Drawing
from erpnext import get_default_company
from obarcode.utils import _now_ms,random_string, oLogger
from frappe.utils.file_manager import save_file
import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics



class BarcodePrinting(Document):
	@frappe.whitelist()
	def get_item_details(self, args=None, for_update=False):
		item = frappe.db.sql("""select i.name, i.stock_uom, i.description, i.image, i.item_name, i.item_group,
				i.has_batch_no, i.sample_quantity, i.has_serial_no, i.allow_alternative_item,
				id.expense_account, id.buying_cost_center
			from `tabItem` i LEFT JOIN `tabItem Default` id ON i.name=id.parent and id.company=%s
			where i.name=%s
				and i.disabled=0
				and (i.end_of_life is null or i.end_of_life='0000-00-00' or i.end_of_life > %s)""",
			(self.company, args.get('item_code'), nowdate()), as_dict = 1)

		if not item:
			frappe.throw(_("Item {0} is not active or end of life has been reached").format(args.get("item_code")))

		item = item[0]

		cart_settings = get_shopping_cart_settings()
		price = get_price(
				args.get('item_code'), cart_settings.price_list, cart_settings.default_customer_group, cart_settings.company
			)

		item_rate = 0
		if price:
			item_rate =  price.get('price_list_rate')

		ret = frappe._dict({
			'uom'			      	: item.stock_uom,
			'stock_uom'				: item.stock_uom,
			'description'		  	: item.description,
			'image'					: item.image,
			'item_name' 		  	: item.item_name,
			'qty'					: args.get("qty"),
			# 'rate'					: item_rate,
			'conversion_factor'		: 1,
			'batch_no'				: '',
			'actual_qty'			: 0,
			'basic_rate'			: item_rate,
			'serial_no'				: '',
			'has_serial_no'			: item.has_serial_no,
			'has_batch_no'			: item.has_batch_no,
			'sample_quantity'		: item.sample_quantity
		})

		return ret

	@frappe.whitelist()
	def printer_test(self):

		merger = PdfFileMerger()
		# merger.setPageLayout("/TwoColumnLeft")

		xLabel = 50*mm
		yLabel = 25*mm
		fileName = f'{_now_ms()}.pdf'
		for item in self.items:
			# creating a pdf object
			pdf = canvas.Canvas(fileName,pagesize=(xLabel,yLabel))
			string = item.barcode
			pdf.setFillColorRGB(0,0,0) # change colors of text here
			pdf.setFont("Courier-Bold", 8)
			# 	barcode = code39.Extended39(string) # code39 type barcode generation here
			# 	barcode = code128.Code128(string, humanReadable=True)
			# 	barcode.drawOn(pdf, x_var*mm , y_var*mm) # coordinates for barcode?
			barcode_eanbc13 = eanbc.Ean13BarcodeWidget(string,barHeight=yLabel/2)
			d = Drawing(xLabel,20*mm)
			d.add(barcode_eanbc13)
			# d.drawOn(pdf, xLabel*0.20, yLabel*0.20)
			d.drawOn(pdf, 20, 20)
			company_name = get_default_company()
			pdf.drawCentredString(xLabel/2, yLabel*0.85, company_name)
			pdf.drawCentredString(xLabel/2, yLabel*0.10, item.item_name)
			pdf.rotate(90)
			pdf.drawCentredString(yLabel/2, -xLabel*0.10, f'QR {item.rate}')
			pdf.save()
			f1 = PdfFileReader(open(fileName, 'rb'))
			merger.append(f1)

		mFileName = f'{_now_ms()}.pdf'
		merger.setPageLayout(layout = "/TwoColumnLeft")
		merger.write(mFileName)

		f1 = open(mFileName, 'rb')
		to_name = random_string(random.randint(8,13),"1234567890ABCDEFGHIJKLMNOPQRSTUVWXYZ").zfill(13)
		file_name = "{}.pdf".format(to_name.replace(" ", "-").replace("/", "-"))
		save_file(file_name, f1.read(), self.doctype,self.name, is_private=1)
		if os.path.exists(fileName):os.remove(fileName)
		if os.path.exists(mFileName):os.remove(mFileName)

	@frappe.whitelist()
	def generate_item_barcode(self,qty=1,x=50,y=25):
		"""
			Generate Item Barcode
		"""
		pdfmetrics.registerFont(TTFont('Arabic', f'{os.path.dirname(__file__)}/fonts/29ltbukraregular.ttf'))

		#init the style sheet
		# styles = getSampleStyleSheet()
		xLabel = float(x)*mm
		yLabel = float(y)*mm
		merger = PdfFileMerger()

		barcodeDrawOnX = 20
		barcodeDrawOnY = 20
		barcodeBarHeight = yLabel/2
		fontSize = 8


		if cint(x) == 38:
			barcodeDrawOnX = xLabel*0.05
			barcodeDrawOnY = 20
			barcodeBarHeight = yLabel * 0.45
			fontSize = 6

		# oLogger.debug('-------------xxxxxxxxxxxxxxxxx--------------')
		# oLogger.debug(f'dirname - {os.path.dirname(__file__)}')
		# oLogger.debug(f'xLabel - {xLabel}')
		# oLogger.debug(f'yLabel - {yLabel}')
		# oLogger.debug(f'barcodeDrawOnX - {barcodeDrawOnX}')
		# oLogger.debug(f'barcodeDrawOnY - {barcodeDrawOnY}')
		# oLogger.debug(f'barcodeBarHeight - {barcodeBarHeight}')
		# oLogger.debug(f'fontSize - {fontSize}')


		# product_info = get_product_info_for_website(item_code).get('product_info') # get_product_info_for_website
		# price = product_info.get('price') #formatted_price

		# app_logo_url = "/assets/obarcode/fonts/29ltbukraregular.ttf"

		cart_settings = get_shopping_cart_settings()
		currency = frappe.db.get_value("Price List", cart_settings.price_list, "currency")
		# oLogger.debug(product_info)
		# oLogger.debug(price)

		# if price:
		# 	item_rate =  price.get('formatted_price')
			# oLogger.debug(item_rate)


		fileName = f'{_now_ms()}.pdf'
		company_name = get_default_company()

		oLogger.debug(self.items)
		for item in self.items:
			oLogger.debug(item)
			# item = frappe.get_doc("Barcode Generator Items",item)
			if item.rate:
				item_rate = fmt_money(item.rate, currency=currency)
			else:
				item_rate = ''
			for i in range(int(qty)):
				# creating a pdf object
				pdf = canvas.Canvas(fileName,pagesize=(xLabel,yLabel))
				string = item.barcode
				pdf.setFillColorRGB(0,0,0) # change colors of text here
				pdf.setFont("Courier-Bold", fontSize)
				#   from reportlab.graphics.barcode import eanbc,code39,code128
				# 	barcode = code39.Extended39(string) # code39 type barcode generation here
				# 	barcode = code128.Code128(string, humanReadable=True)
				# 	barcode.drawOn(pdf, x_var*mm , y_var*mm) # coordinates for barcode?
				try:
					barcode_eanbc13 = eanbc.Ean13BarcodeWidget(string,barHeight=barcodeBarHeight,fontSize = fontSize)
				except Exception as ex:
					oLogger.debug(ex)
					continue
				d = Drawing(xLabel,20*mm)
				d.add(barcode_eanbc13)
				# d.drawOn(pdf, xLabel*0.20, yLabel*0.20)
				d.drawOn(pdf, barcodeDrawOnX, barcodeDrawOnY)
				pdf.drawCentredString(xLabel/2, yLabel*0.85, company_name)
				pdf.drawCentredString(xLabel/2, yLabel*0.10, item.item_name)
				pdf.rotate(90)
				pdf.setFont("Arabic", fontSize-1)
				rehaped_text = arabic_reshaper.reshape(item_rate)
				bidi_text = get_display(rehaped_text)
				pdf.drawCentredString(yLabel*0.60, -xLabel*0.10, bidi_text)
				pdf.save()
				f1 = PdfFileReader(open(fileName, 'rb'))
				merger.append(f1)

		mFileName = f'{_now_ms()}.pdf'
		merger.setPageLayout(layout = "/TwoColumnLeft")
		merger.write(mFileName)
		f1 = open(mFileName, 'rb')
		# to_name = random_string(random.randint(1,6),"1234567890ABCDEFGHIJKLMNOPQRSTUVWXYZ").zfill(6)
		# file_name = "{}-{}.pdf".format(item_barcode,to_name.replace(" ", "-").replace("/", "-"))
		file_name = f'{_now_ms()}-{qty}-{x}x{y}.pdf'
		save_file(file_name, f1.read(), self.doctype, self.name , is_private=1)
		if os.path.exists(fileName):os.remove(fileName)
		if os.path.exists(mFileName):os.remove(mFileName)
		# oLogger.debug('-------------xxxxxxxxxxxxxxxxx--------------')

@frappe.whitelist()
def pr_make_barcode(source_name, target_doc=None):
	doc = get_mapped_doc("Purchase Receipt", source_name, {
		"Purchase Receipt": {
			"doctype": "Barcode Printing",
			"validation": {
				"docstatus": ["=", 1]
			}
		},
		"Purchase Receipt Item": {
			"doctype": "Barcode Generator Items",
			"field_map": {
				"stock_qty": "qty",
				"batch_no": "batch_no",
				"parent": "ref_pr",
				"price_list_rate":"basic_rate",
				"serial_no":"serial_no",
				"batch_no":"batch_no",
				"set_warehouse":"warehouse"
			},
		}
	}, target_doc)

	return doc

@frappe.whitelist()
def se_make_barcode(source_name, target_doc=None):

	def check_manufacturing(d):
		if frappe.get_doc("Stock Entry",d.parent).stock_entry_type == "Manufacture":
			return  (d.t_warehouse != None)
		return 1

	doclist = get_mapped_doc("Stock Entry", source_name, {
		"Stock Entry": {
			"doctype": "Barcode Printing",
			"validation": {
				"docstatus": ["=", 1],
			},
			"field_map": {
				"get_items_from" :"doctype"
			}
		},
		"Stock Entry Detail": {
			"doctype": "Barcode Generator Items",
			"field_map": {
				"valuation_rate":"rate",
				"qty": "qty",
				"uom": "uom",
				"parent": "ref_se",
				"serial_no":"serial_no",
				"batch_no":"batch_no",
				"additional_cost":"additional_cost"	,
				"t_warehouse":"warehouse"
			},
			"condition":check_manufacturing
		}
	}, target_doc)

	return doclist

@frappe.whitelist()
def search_item_serial_or_batch_or_barcode_number(search_value,item):
	# search barcode no
	item = json.loads(item)
	barcode_data = frappe.db.get_value('Item Barcode', {'parent': item["item_code"]}, ['barcode', 'barcode_type', 'parent as item_code'], as_dict=True)
	if barcode_data:
		if barcode_data.barcode_type == "EAN":
			barcode_data.barcode_type = "EAN13"
		elif barcode_data.barcode_type == "UPC-A":
			barcode_data.barcode_type = "UPC"
		return barcode_data

	# search serial no
	serial_no_data = frappe.db.get_value('Serial No', search_value, ['name as serial_no', 'item_code'], as_dict=True)
	if serial_no_data:
		return serial_no_data

	# search batch no
	batch_no_data = frappe.db.get_value('Batch', search_value, ['name as batch_no', 'item as item_code'], as_dict=True)
	if batch_no_data:
		return batch_no_data

	return {}


# @frappe.whitelist()
# def printer_test():
# 	import win32com.client
# 	o = win32com.client.Dispatch("WScript.Network")
# 	prlist = o.EnumPrinterConnections()
# 	for pr in prlist:
# 		print(pr)

# 	return prlist




@frappe.whitelist()
def get_item_details(frm):
	items = frm.doc.items
	item_code_list = [d.get("item_code") for d in items if d.get("item_code")]
	item = frappe.db.sql("""select barcode, barcode_type
		from `tabItem Barcode`
		where i.parent=%s""",
		format(frappe.db.escape(frm.item_code)), as_dict = 1)

	if not item:
		frappe.throw(_("Item {0} is not active or end of life has been reached"))

	item = item[0]

	return item

@frappe.whitelist()
def create_barcode_printing(throw_if_missing, se_id,pr_id):
	bp = frappe.new_doc('Barcode Printing')

	if(se_id):
		se = frappe.get_doc("Stock Entry", se_id)
		for item in se.items:
			if 	item.t_warehouse != None:
				row = bp.append('items', {})
				row.item_code = item.item_code
				row.qty = item.qty
				row.basic_rate = item.basic_rate
				row.rate = item.valuation_rate
				row.uom = item.uom
				row.additional_cost = item.additional_cost
				row.conversion_factor = item.conversion_factor
				row.serial_no = item.serial_no
				row.batch_no = item.batch_no
				row.ref_se = se_id

	if(pr_id):
		pr = frappe.get_doc("Purchase Receipt",pr_id)
		for item in pr.items:
			row = bp.append('items', {})
			row.item_code = item.item_code
			row.qty = item.qty
			row.basic_rate = item.price_list_rate
			row.rate = item.rate
			row.uom = item.uom
			row.serial_no = item.serial_no
			row.batch_no = item.batch_no
			row.ref_pr = pr_id
			row.warehouse = pr.set_warehouse

	bp.insert(
		ignore_mandatory=True
		)

	if not frappe.db.exists(bp.doctype, bp.name):
		if throw_if_missing:
			frappe.throw('Linked document (Stock Entry / Purchase Receipt) not found')
	return frappe.get_doc(bp.doctype, bp.name)

@frappe.whitelist()
def make_qrcode(doc, route):
	qr_html = ''
	barcode_doc = frappe.get_doc("Barcode Printing", json.loads(doc)["name"])
	items = barcode_doc.items
	for item in items:
		if item.get("qty")!= 0:
			if item.get("serial_no"):
				serials = item.get("serial_no").split("\n")
				if serials[-1] == '':
					serials.pop()
				for serial in serials:
					uri  = "item_qr?"
					if item.get("item_code"): uri += "item_code=" + urllib.parse.quote(item.get_formatted("item_code"))
					if item.get("barcode"): uri += "&barcode=" + urllib.parse.quote(item.get_formatted("barcode"))
					if serial: uri += "&serial_no=" + urllib.parse.quote(serial)
					if item.get("batch_no"): uri += "&batch_no=" + urllib.parse.quote(item.get_formatted("batch_no"))
					# if item.get("rate"): uri += "&rate=" + urllib.parse.quote(item.get_formatted("rate"))
					img_str = qr_code_img(uri,route)
					qr_html += '<img src="' + "data:image/png;base64,{0}".format(img_str.decode("utf-8")) + '" width="240px"/><br>'
			else:
				uri  = "item_qr?"
				if item.get("item_code"): uri += "item_code=" + urllib.parse.quote(item.get_formatted("item_code"))
				if item.get("barcode"): uri += "&barcode=" + urllib.parse.quote(item.get_formatted("barcode"))
				if item.get("batch_no"): uri += "&batch_no=" + urllib.parse.quote(item.get_formatted("batch_no"))
				# if item.get("rate"): uri += "&rate=" + urllib.parse.quote(item.get_formatted("rate"))
				img_str = qr_code_img(uri,route)
				qr_html += '<img src="' + "data:image/png;base64,{0}".format(img_str.decode("utf-8")) + '" width="240px"/><br>'
	return qr_html

def qr_code_img(uri,route):
	qr_config = frappe.get_doc("QR Code Configuration")
	qr = qrcode.QRCode(
		border=qr_config.border,
		error_correction=qrcode.constants.ERROR_CORRECT_H,
	)
	url = route + "/" + uri
	qr.add_data(url)
	qr.make(fit=True)
	logo = qr_config.logo

	img = qr.make_image(fill_color = qr_config.fill, back_color = qr_config.background)
	w,h = img.size
	if logo:
		logo = Image.open(requests.get(get_url(logo,None), stream=True).raw).resize((w//4, h//4))
		pos = ((img.size[0] - logo.size[0]) // 2, (img.size[1] - logo.size[1]) // 2)
		img.paste(logo, pos)

	buffered = BytesIO()
	img.save(buffered, format="PNG")
	buffered.seek(0)
	img_str = base64.b64encode(buffered.read())
	return img_str


