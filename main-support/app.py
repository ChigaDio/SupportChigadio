from cmath import isfinite, isnan
from venv import logger
from flask import Flask, send_from_directory, jsonify, request
import os
import json

app = Flask(__name__, static_folder='build')
DATA_DIR = 'data'
ENUM = 'enum'

# ディレクトリが存在しない場合に作成
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)
    
file_path = os.path.join(DATA_DIR, ENUM)    
# ディレクトリが存在しない場合に作成
if not os.path.exists(file_path):
    os.makedirs(file_path)

# APIエンドポイント（POST/GET/PATCH）
@app.route('/api/enum-id', methods=['GET', 'POST', 'PATCH'])
def manage_enum_id():
    file_path = os.path.join(DATA_DIR, ENUM)
    file_path = os.path.join(file_path, 'enum_list.json')
    
    if request.method == 'GET':
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            return jsonify(data)
        except FileNotFoundError:
            return jsonify([]), 404
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    elif request.method == 'POST':
        try:
            new_enum = request.get_json()
            if not new_enum or not new_enum.get('name'):
                return jsonify({"error": "Enum name is required"}), 400
            # 既存のリストを読み込む
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
            except FileNotFoundError:
                data = []
            # 重複チェック
            if any(item['name'] == new_enum['name'] for item in data):
                return jsonify({"error": f"Enum {new_enum['name']} already exists"}), 400
            # 新しいIDを生成
            max_id = max([item['id'] for item in data], default=0) + 1
            new_enum_entry = {"id": max_id, "name": new_enum['name']}
            data.append(new_enum_entry)
            # enum_list.json に保存
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
                
            file_path = os.path.join(DATA_DIR, ENUM)
            new_directory_path = os.path.join(file_path, new_enum['name'])
            os.mkdir(new_directory_path)
            # 個別の <enum_name>.json を作成（空配列）
            with open(os.path.join(new_directory_path, f"{new_enum['name']}.json"), 'w') as f:
                json.dump([], f, indent=2)
            return jsonify({"message": f"Enum {new_enum['name']} created successfully", "data": new_enum_entry})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    elif request.method == 'PATCH':
        try:
            delete_name = request.get_json()['name']
            with open(file_path, 'r') as f:
                data = json.load(f)
            data = [item for item in data if item['name'] != delete_name]
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
            return jsonify({"message": f"Enum {delete_name} removed from enum_list.json"})
        except FileNotFoundError:
            return jsonify({"error": "enum_list.json not found"}), 404
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        
@app.route('/api/generate-enum/<name>', methods=['POST'])
def generate_enum_cs(name):
    try:
        data = request.get_json()
        logger.debug(f"Generating C# enum for {name}: {data}")
        # valueが数字のみのデータをフィルタ
        valid_data = [item for item in data if not isnan(item['value']) and isfinite(item['value'])]
        # C#コードを生成
        cs_content = f"public enum {name} {{\n"
        cs_content += "    None = -1, // デフォルト値\n"
        for item in valid_data:
            cs_content += f"    {item['property']} = {item['value']}, // {item['description']}\n"
        max_value = max([item['value'] for item in valid_data], default=-1) + 1
        cs_content += f"    Max = {max_value}\n"
        cs_content += "}"
        # ファイルに保存
        file_path = os.path.join(DATA_DIR,  ENUM)
        file_path = os.path.join(file_path, f'{name}')
        file_path = os.path.join(file_path, f'{name}.cs')
        with open(file_path, 'w',encoding='utf-8') as f:
            f.write(cs_content)
        logger.info(f"Generated {name}.cs")
        return jsonify({"message": f"{name}.cs generated successfully"})
    except Exception as e:
        logger.error(f"Error generating {name}.cs: {str(e)}")
        return jsonify({"error": str(e)}), 500

# 詳細エンドポイント
@app.route('/api/enum/<name>', methods=['GET', 'POST', 'DELETE'])
def manage_enum_detail(name):
    file_path = os.path.join(DATA_DIR,  ENUM)
    file_path = os.path.join(file_path, f'{name}')
    file_path = os.path.join(file_path, f'{name}.json')
    
    if request.method == 'GET':
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
            return jsonify(data)
        except FileNotFoundError:
            return jsonify([]), 404
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    elif request.method == 'POST':
        try:
            data = request.get_json()
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2)
            return jsonify({"message": f"{name}.json saved successfully"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    elif request.method == 'DELETE':
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                os.removedirs(file_path + "/../")
                file_path = os.path.join(DATA_DIR,  ENUM)
                # enum_list.json からも削除
                with open(os.path.join(file_path, 'enum_list.json'), 'r') as f:
                    data = json.load(f)
                data = [item for item in data if item['name'] != name]
                with open(os.path.join(file_path, 'enum_list.json'), 'w') as f:
                    json.dump(data, f, indent=2)
                return jsonify({"message": f"{name}.json deleted successfully"})
            return jsonify({"error": f"{name}.json not found"}), 404
        except Exception as e:
            return jsonify({"error": str(e)}), 500

# 静的ファイルのルーティング（最後に定義）
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_static(path):
    if path != '' and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, 'index.html')

if __name__ == '__main__':
    app.run(debug=True, port=8000)