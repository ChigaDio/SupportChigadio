# -*- coding: utf-8 -*-
"""
pythonSrc/behavior_routes.py

Behavior Tree の管理API（実処理は pythonSrc/behavior.py に委譲する薄いルート層）。
- /api/behavior-data, /api/behavior-data/<name>, /api/behavior-generate/<name>

app.py から `pythonSrc.behavior_routes.register(app, DATA_DIR)` を呼び出して有効化する。
"""
import logging

from flask import Blueprint, request

import pythonSrc.behavior
from pythonSrc.data_utils import get_type_lists

logger = logging.getLogger(__name__)
bp = Blueprint('behavior_routes', __name__)

# app.py 側の register(app, DATA_DIR) で設定される（pythonSrc.behavior 側は独自にDATA_DIRを解決する）
DATA_DIR = None

def init(data_dir):
    """app.py から呼び出す初期化関数。"""
    global DATA_DIR
    DATA_DIR = data_dir


# Behavior Tree API (追加部分)



@bp.route('/api/behavior-data', methods=['GET'])
def get_behavior_data():
    return pythonSrc.behavior.get_behavior_data()

@bp.route('/api/behavior-data', methods=['POST'])
def add_behavior():
    return pythonSrc.behavior.add_behavior(request)


@bp.route('/api/behavior-data/<name>', methods=['DELETE'])
def delete_behavior(name):
    return pythonSrc.behavior.delete_behavior()

@bp.route('/api/behavior-data/<name>', methods=['GET'])
def get_behavior_detail(name):
    return pythonSrc.behavior.get_behavior_detail(name)

@bp.route('/api/behavior-data/<name>', methods=['PUT'])
def save_behavior_detail(name):
    return pythonSrc.behavior.save_behavior_detail(name,request)

@bp.route('/api/behavior-generate/<name>', methods=['POST'])
def generate_behavior_code(name):
    basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data = get_type_lists()
    return pythonSrc.behavior.generate_behavior_code(name,basic_types, unity_types, enum_list, class_list, class_data_id_list,enum_data,class_data_id,class_data)


def register(app, data_dir):
    """app.py から呼び出し、DATA_DIR を設定した上でルートを登録する。"""
    global DATA_DIR
    DATA_DIR = data_dir
    app.register_blueprint(bp)
