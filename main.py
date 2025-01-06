from subprocess import run as subprocess_run
from time import sleep as time_sleep
from _thread import interrupt_main
from qrcode import QRCode
from zeroconf import IPVersion, ServiceBrowser, ServiceStateChange, Zeroconf
from adbutils import adb
PASSWORD   = "jenil"
device_ports = []
def pair_device(address: str, port: int):
    print("Pairing...")
    if subprocess_run(["adb", "pair", f"{address}:{port}", PASSWORD], capture_output=True).returncode != 0:
        print("Pairing failed.")
        return
    print("Paired.")
def connect_device(address: str, port: int):
    print("Connecting...")
    if subprocess_run(["adb", "connect", f"{address}:{port}"], capture_output=True).returncode != 0:
        print("Connecting failed.")
        return
    print("Connected.")
    interrupt_main()
def on_service_state_change(zeroconf: Zeroconf,service_type: str,name: str,state_change: ServiceStateChange) -> None:
    if state_change is ServiceStateChange.Added:
        info = zeroconf.get_service_info(service_type, name)
        if not info:
            return
        addr = info.parsed_addresses()[0]
        if service_type == "_adb-tls-pairing._tcp.local.":
            if not device_ports:
                return
            pair_port = info.port or 5555
            connect_port = device_ports[0]
            pair_device(addr, pair_port)
            connect_device(addr, connect_port)
        elif service_type == "_adb-tls-connect._tcp.local.":
            device_ports.append(info.port)
if adb.device_list().__len__() == 0:
    qr = QRCode(border=1, box_size=10, version=1)
    qr.add_data(f"WIFI:T:ADB;S:ADB_WIFI_jenilproject;P:{PASSWORD};;")
    qr.print_ascii(invert=True)
    zc = Zeroconf(ip_version=IPVersion.V4Only)
    ServiceBrowser(zc=zc,type_=["_adb-tls-connect._tcp.local.", "_adb-tls-pairing._tcp.local."],handlers=[on_service_state_change])
    try:
        while True:
            time_sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        zc.close()






from uiautomator2 import connect as u2_connect
from flask import Flask,Blueprint, request, url_for , redirect
from urllib.parse import urljoin
from pathlib import Path
app = Flask(__name__,static_folder="")
app.config["SECRET_KEY"] = "e456cc80ebd6409b90cb4c3ef70817b9"
devices = {}

def response_make(**kwargs):
    res = {
        'status':0,
        'code':200000,
        'message':'success',
        'data':None
    }
    res.update(**kwargs)
    return res
bp_device = Blueprint('bp_device', __name__, url_prefix='/api/android/device')
def get_device():
    return devices.get(request.get_json().get('serial'))
@bp_device.route('/list', methods=['GET'])
def device_list():
    return response_make(data=[d.serial for d in adb.device_list()])
@bp_device.route('/connect', methods=['POST'])
def connect():
    serial = request.get_json().get('serial')
    devices[serial] = u2_connect(serial)
    return response_make()
@bp_device.route('/dump', methods=['POST'])
def dump():
    device = get_device()
    if device is None:
        return response_make(status=-1,code=400000,message='Device offline')
    hierarchy_xml = device.dump_hierarchy()
    Path(app.static_folder,"window.xml").write_text(hierarchy_xml)
    device.screenshot(Path(app.static_folder,"window.png").__str__())
    info = device.info
    return response_make(data={
        'imageURL':urljoin(request.host_url,url_for('static',filename="window.png")),
        'xml':hierarchy_xml,
        'width':info['displayWidth'],
        'height':info['displayHeight'],
        'rotation': info['displayRotation']%2
    })
@bp_device.route('/call/<func>',methods=['POST'])
def call(func):
    device = get_device()
    payload = request.get_json()
    func_obj = getattr(device,func)
    if callable(func_obj):
        selectors = payload.get('selectors',dict())
        args = payload.get('args',list())
        kwargs = payload.get('kwargs',dict())
        if len(selectors)==0:
            cmd='device.{}'.format(func)
        else:
            cmd='device(**{}).{}'.format(selectors,func)
        if len(args)==0:
            cmd += '(**{})'.format(kwargs)
        else:
            cmd += '(*{},**{})'.format(args,kwargs)
        result = eval(cmd)
    else:
        result = func_obj
    return response_make(data=result)
@bp_device.app_errorhandler(404)
def handler_404(err):
    return response_make(status=-1,code=400000,message=str(err)),404
@bp_device.app_errorhandler(Exception)
def handler_errors(err):
    return response_make(status=-1,code=500000,message=str(err)),500
app.register_blueprint(bp_device)
@app.get("/")
def index():
    return redirect(url_for('static',filename="index.html"))
if __name__ == "__main__":
    app.run(host="0.0.0.0",port=8080)