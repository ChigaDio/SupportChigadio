import os
import sys

# 実行可能ファイルのディレクトリを取得（PyInstaller対応）
if getattr(sys, 'frozen', False):
    # PyInstallerでビルドされた場合
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # デバッグ環境（VS Codeなど）
    # main-support/ の1つ上のディレクトリ（project/）を基準にする
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ディレクトリパスをプロジェクトルート基準に設定
STATIC_FOLDER = os.path.join(BASE_DIR, 'build')
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "data"))
EXPANSION_DIR = os.path.join(DATA_DIR, 'Expansion')
#レーダーチャート
RADAR_CHART_GENERATOR_DIR = os.path.join(EXPANSION_DIR, 'RadarChartGenerator')
RADAR_CHART_GENERATOR_EDITOR_DIR = os.path.join(RADAR_CHART_GENERATOR_DIR, 'Editor')
RADAR_CHART_GENERATOR_RADERCHART_CS = os.path.join(RADAR_CHART_GENERATOR_DIR, 'RadarChart.cs')
RADAR_CHART_GENERATOR_RADARCHARTCONTROLLER_CS = os.path.join(RADAR_CHART_GENERATOR_DIR, 'RadarChartController.cs')
RADAR_CHART_GENERATOR_RADERCHARTGENERATORWINDOW_CS = os.path.join(RADAR_CHART_GENERATOR_EDITOR_DIR, 'RadarChartGeneratorWindow.cs')

def get_static_file_path():
    if not os.path.exists(EXPANSION_DIR):
        os.mkdir(EXPANSION_DIR)
    if not os.path.exists(RADAR_CHART_GENERATOR_DIR):
        os.mkdir(RADAR_CHART_GENERATOR_DIR)
    if not os.path.exists(RADAR_CHART_GENERATOR_EDITOR_DIR):
        os.mkdir(RADAR_CHART_GENERATOR_EDITOR_DIR)
        
    if not os.path.exists(RADAR_CHART_GENERATOR_RADERCHART_CS):
        with open(RADAR_CHART_GENERATOR_RADERCHART_CS, 'w', encoding='utf-8') as f:
            code = """
            using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

namespace RadarChartGenerator
{
    /// <summary>
    /// レーダーチャート（多角形グラフ）描画コンポーネント
    /// UICanvasのImageコンポーネントと連携して動作します
    /// </summary>
    [RequireComponent(typeof(CanvasRenderer))]
    public class RadarChart : MaskableGraphic
    {
        // =====================
        // 基本設定
        // =====================
        [Header("基本設定")]
        [Tooltip("頂点数 (3〜12)")]
        [Range(3, 12)]
        public int vertexCount = 5;

        [Tooltip("分割数（同心多角形の数）")]
        [Range(1, 10)]
        public int divisions = 5;

        [Tooltip("チャートの半径")]
        public float radius = 180f;

        [Tooltip("各頂点の値 (0.0〜1.0)")]
        public List<float> values = new List<float> { 0.8f, 0.6f, 0.9f, 0.5f, 0.7f };

        // =====================
        // 塗りつぶし設定
        // =====================
        [Header("塗りつぶし設定")]
        public FillMode fillMode = FillMode.SingleColor;

        [Tooltip("単色モード時の塗りつぶし色")]
        public Color fillColor = new Color(0.2f, 0.5f, 1f, 0.4f);

        [Tooltip("グラデーション（外側→内側）")]
        public Gradient fillGradient = new Gradient();

        [Tooltip("各頂点の個別色（VertexColorモード時）")]
        public List<Color> vertexColors = new List<Color>();

        [Tooltip("グラデーション分割精度（高いほど滑らか）")]
        [Range(2, 32)]
        public int gradientSteps = 16;

        // =====================
        // アウトライン設定
        // =====================
        [Header("アウトライン設定")]
        [Tooltip("データポリゴンのアウトライン表示")]
        public bool showOutline = true;

        [Tooltip("アウトラインの色")]
        public Color outlineColor = new Color(0.2f, 0.5f, 1f, 1f);

        [Tooltip("アウトラインの太さ")]
        [Range(0.5f, 8f)]
        public float outlineWidth = 2f;

        // =====================
        // グリッド設定
        // =====================
        [Header("グリッド設定")]
        [Tooltip("グリッド（同心多角形）の表示")]
        public bool showGrid = true;

        [Tooltip("グリッドの色")]
        public Color gridColor = new Color(0.5f, 0.5f, 0.5f, 0.4f);

        [Tooltip("グリッド線の太さ")]
        [Range(0.5f, 4f)]
        public float gridLineWidth = 1f;

        // =====================
        // 軸線設定
        // =====================
        [Header("軸線設定")]
        [Tooltip("中心から各頂点への軸線を表示")]
        public bool showAxes = true;

        [Tooltip("軸線の色")]
        public Color axisColor = new Color(0.5f, 0.5f, 0.5f, 0.5f);

        [Tooltip("軸線の太さ")]
        [Range(0.5f, 4f)]
        public float axisLineWidth = 1f;

        // =====================
        // アニメーション設定
        // =====================
        [Header("アニメーション")]
        [Tooltip("値の変化をアニメーションで補間する")]
        public bool animateChanges = true;

        [Tooltip("アニメーション速度")]
        [Range(0.5f, 10f)]
        public float animationSpeed = 3f;

        // =====================
        // 内部変数
        // =====================
        private List<float> _currentValues = new List<float>();
        private List<float> _targetValues = new List<float>();
        private bool _isAnimating = false;
        private float _startAngle = -Mathf.PI / 2f; // 上から開始

        public enum FillMode
        {
            SingleColor,
            RadialGradient,
            VertexColor
        }

        // =====================
        // 初期化
        // =====================
        protected override void Start()
        {
            base.Start();
            InitializeValues();
            SetVertexDefault();
        }

        private void InitializeValues()
        {
            _currentValues.Clear();
            _targetValues.Clear();
            SyncValueCount();
            for (int i = 0; i < vertexCount; i++)
            {
                float v = (i < values.Count) ? Mathf.Clamp01(values[i]) : 0.5f;
                _currentValues.Add(v);
                _targetValues.Add(v);
            }
        }

        private void SyncValueCount()
        {
            while (values.Count < vertexCount) values.Add(0.5f);
            while (vertexColors.Count < vertexCount) vertexColors.Add(Color.white);
        }

        private void SetVertexDefault()
        {
            if (fillGradient == null || fillGradient.colorKeys.Length == 0)
            {
                var gradient = new Gradient();
                gradient.SetKeys(
                    new GradientColorKey[]
                    {
                        new GradientColorKey(new Color(0.2f, 0.5f, 1f), 0f),
                        new GradientColorKey(new Color(0.5f, 0.8f, 1f), 1f)
                    },
                    new GradientAlphaKey[]
                    {
                        new GradientAlphaKey(0.8f, 0f),
                        new GradientAlphaKey(0.2f, 1f)
                    }
                );
                fillGradient = gradient;
            }
        }

        // =====================
        // 毎フレーム更新
        // =====================
        private void Update()
        {
            if (!animateChanges || !_isAnimating) return;

            bool stillAnimating = false;
            for (int i = 0; i < _currentValues.Count && i < _targetValues.Count; i++)
            {
                float diff = _targetValues[i] - _currentValues[i];
                if (Mathf.Abs(diff) > 0.001f)
                {
                    _currentValues[i] += diff * Time.deltaTime * animationSpeed;
                    stillAnimating = true;
                }
                else
                {
                    _currentValues[i] = _targetValues[i];
                }
            }
            _isAnimating = stillAnimating;
            SetVerticesDirty();
        }

        // =====================
        // 値の外部設定API
        // =====================
        /// <summary>
        /// 指定インデックスの値をセット（0.0〜1.0）
        /// </summary>
        public void SetValue(int index, float value)
        {
            SyncValueCount();
            if (index < 0 || index >= vertexCount) return;
            value = Mathf.Clamp01(value);
            values[index] = value;

            if (index < _targetValues.Count)
                _targetValues[index] = value;
            else
                while (_targetValues.Count <= index) _targetValues.Add(value);

            if (!animateChanges)
            {
                if (index < _currentValues.Count)
                    _currentValues[index] = value;
                else
                    while (_currentValues.Count <= index) _currentValues.Add(value);
            }
            _isAnimating = true;
            SetVerticesDirty();
        }

        /// <summary>
        /// 全頂点の値を一括セット
        /// </summary>
        public void SetAllValues(List<float> newValues)
        {
            SyncValueCount();
            for (int i = 0; i < vertexCount; i++)
            {
                float v = (i < newValues.Count) ? Mathf.Clamp01(newValues[i]) : 0f;
                values[i] = v;
                if (i < _targetValues.Count) _targetValues[i] = v;
                else _targetValues.Add(v);
                if (!animateChanges)
                {
                    if (i < _currentValues.Count) _currentValues[i] = v;
                    else _currentValues.Add(v);
                }
            }
            _isAnimating = true;
            SetVerticesDirty();
        }

        /// <summary>
        /// 頂点数を動的に変更
        /// </summary>
        public void SetVertexCount(int count)
        {
            count = Mathf.Clamp(count, 3, 12);
            vertexCount = count;
            InitializeValues();
            SetVerticesDirty();
        }

        // =====================
        // 描画メイン
        // =====================
        protected override void OnPopulateMesh(VertexHelper vh)
        {
            vh.Clear();
            SyncValueCount();
            if (_currentValues.Count < vertexCount)
                InitializeValues();

            Vector2 center = Vector2.zero;

            // 描画順序：グリッド → 軸線 → データポリゴン → アウトライン
            if (showGrid) DrawGrid(vh, center);
            if (showAxes) DrawAxes(vh, center);
            DrawDataPolygon(vh, center);
            if (showOutline) DrawOutline(vh, center);
        }

        // =====================
        // グリッド（同心多角形）描画
        // =====================
        private void DrawGrid(VertexHelper vh, Vector2 center)
        {
            for (int d = 1; d <= divisions; d++)
            {
                float r = radius * d / divisions;
                DrawPolygonOutline(vh, center, r, vertexCount, gridColor, gridLineWidth);
            }
        }

        // =====================
        // 軸線描画
        // =====================
        private void DrawAxes(VertexHelper vh, Vector2 center)
        {
            for (int i = 0; i < vertexCount; i++)
            {
                float angle = _startAngle + (2f * Mathf.PI * i / vertexCount);
                Vector2 tip = center + new Vector2(Mathf.Cos(angle), Mathf.Sin(angle)) * radius;
                DrawLine(vh, center, tip, axisLineWidth, axisColor);
            }
        }

        // =====================
        // データポリゴン描画
        // =====================
        private void DrawDataPolygon(VertexHelper vh, Vector2 center)
        {
            switch (fillMode)
            {
                case FillMode.SingleColor:
                    DrawPolygonFillSingleColor(vh, center);
                    break;
                case FillMode.RadialGradient:
                    DrawPolygonFillGradient(vh, center);
                    break;
                case FillMode.VertexColor:
                    DrawPolygonFillVertexColor(vh, center);
                    break;
            }
        }

        private void DrawPolygonFillSingleColor(VertexHelper vh, Vector2 center)
        {
            int baseIndex = vh.currentVertCount;
            UIVertex centerVert = UIVertex.simpleVert;
            centerVert.position = center;
            centerVert.color = fillColor;
            vh.AddVert(centerVert);

            for (int i = 0; i < vertexCount; i++)
            {
                float angle = _startAngle + (2f * Mathf.PI * i / vertexCount);
                float val = GetCurrentValue(i);
                Vector2 pos = center + new Vector2(Mathf.Cos(angle), Mathf.Sin(angle)) * radius * val;
                UIVertex v = UIVertex.simpleVert;
                v.position = pos;
                v.color = fillColor;
                vh.AddVert(v);
            }
            for (int i = 0; i < vertexCount; i++)
            {
                vh.AddTriangle(baseIndex, baseIndex + 1 + i, baseIndex + 1 + (i + 1) % vertexCount);
            }
        }

        private void DrawPolygonFillGradient(VertexHelper vh, Vector2 center)
        {
            // 放射状グラデーション: 同心リングを重ねて近似
            for (int step = 0; step < gradientSteps; step++)
            {
                float t0 = (float)step / gradientSteps;
                float t1 = (float)(step + 1) / gradientSteps;
                Color c0 = fillGradient.Evaluate(1f - t0); // 内側
                Color c1 = fillGradient.Evaluate(1f - t1); // 外側

                int baseIdx = vh.currentVertCount;
                for (int i = 0; i < vertexCount; i++)
                {
                    float angle = _startAngle + (2f * Mathf.PI * i / vertexCount);
                    float val = GetCurrentValue(i);
                    Vector2 inner = center + new Vector2(Mathf.Cos(angle), Mathf.Sin(angle)) * radius * val * t0;
                    Vector2 outer = center + new Vector2(Mathf.Cos(angle), Mathf.Sin(angle)) * radius * val * t1;
                    UIVertex vi = UIVertex.simpleVert;
                    vi.position = inner; vi.color = c0; vh.AddVert(vi);
                    UIVertex vo = UIVertex.simpleVert;
                    vo.position = outer; vo.color = c1; vh.AddVert(vo);
                }
                // 中心
                if (step == 0)
                {
                    // 最内リングは中心点から
                    UIVertex vc = UIVertex.simpleVert;
                    vc.position = center;
                    vc.color = fillGradient.Evaluate(1f);
                    vh.AddVert(vc);
                    int centerIdx = vh.currentVertCount - 1;
                    for (int i = 0; i < vertexCount; i++)
                    {
                        int cur = baseIdx + i * 2;
                        int nxt = baseIdx + ((i + 1) % vertexCount) * 2;
                        vh.AddTriangle(centerIdx, cur, nxt);
                    }
                }
                else
                {
                    for (int i = 0; i < vertexCount; i++)
                    {
                        int cur0 = baseIdx + i * 2;
                        int cur1 = baseIdx + i * 2 + 1;
                        int nxt0 = baseIdx + ((i + 1) % vertexCount) * 2;
                        int nxt1 = baseIdx + ((i + 1) % vertexCount) * 2 + 1;
                        vh.AddTriangle(cur0, cur1, nxt0);
                        vh.AddTriangle(cur1, nxt1, nxt0);
                    }
                }
            }
            // 最外リング
            {
                int baseIdx = vh.currentVertCount;
                Color outerColor = fillGradient.Evaluate(0f);
                for (int i = 0; i < vertexCount; i++)
                {
                    float angle = _startAngle + (2f * Mathf.PI * i / vertexCount);
                    float val = GetCurrentValue(i);
                    float t0 = (float)(gradientSteps - 1) / gradientSteps;
                    Vector2 inner = center + new Vector2(Mathf.Cos(angle), Mathf.Sin(angle)) * radius * val * t0;
                    Vector2 outer = center + new Vector2(Mathf.Cos(angle), Mathf.Sin(angle)) * radius * val;
                    Color c0 = fillGradient.Evaluate(1f - t0);
                    UIVertex vi = UIVertex.simpleVert;
                    vi.position = inner; vi.color = c0; vh.AddVert(vi);
                    UIVertex vo = UIVertex.simpleVert;
                    vo.position = outer; vo.color = outerColor; vh.AddVert(vo);
                }
                for (int i = 0; i < vertexCount; i++)
                {
                    int cur0 = baseIdx + i * 2;
                    int cur1 = baseIdx + i * 2 + 1;
                    int nxt0 = baseIdx + ((i + 1) % vertexCount) * 2;
                    int nxt1 = baseIdx + ((i + 1) % vertexCount) * 2 + 1;
                    vh.AddTriangle(cur0, cur1, nxt0);
                    vh.AddTriangle(cur1, nxt1, nxt0);
                }
            }
        }

        private void DrawPolygonFillVertexColor(VertexHelper vh, Vector2 center)
        {
            // 各頂点に指定色、中心はブレンド色
            Color centerColor = Color.black;
            centerColor.a = 0f;
            for (int i = 0; i < vertexCount; i++)
            {
                Color vc = (i < vertexColors.Count) ? vertexColors[i] : fillColor;
                centerColor += vc;
            }
            centerColor /= vertexCount;

            int baseIndex = vh.currentVertCount;
            UIVertex cv = UIVertex.simpleVert;
            cv.position = center;
            cv.color = centerColor;
            vh.AddVert(cv);

            for (int i = 0; i < vertexCount; i++)
            {
                float angle = _startAngle + (2f * Mathf.PI * i / vertexCount);
                float val = GetCurrentValue(i);
                Vector2 pos = center + new Vector2(Mathf.Cos(angle), Mathf.Sin(angle)) * radius * val;
                Color vc = (i < vertexColors.Count) ? vertexColors[i] : fillColor;
                UIVertex v = UIVertex.simpleVert;
                v.position = pos;
                v.color = vc;
                vh.AddVert(v);
            }
            for (int i = 0; i < vertexCount; i++)
            {
                vh.AddTriangle(baseIndex, baseIndex + 1 + i, baseIndex + 1 + (i + 1) % vertexCount);
            }
        }

        // =====================
        // アウトライン描画
        // =====================
        private void DrawOutline(VertexHelper vh, Vector2 center)
        {
            List<Vector2> points = new List<Vector2>();
            for (int i = 0; i < vertexCount; i++)
            {
                float angle = _startAngle + (2f * Mathf.PI * i / vertexCount);
                float val = GetCurrentValue(i);
                points.Add(center + new Vector2(Mathf.Cos(angle), Mathf.Sin(angle)) * radius * val);
            }
            for (int i = 0; i < points.Count; i++)
            {
                DrawLine(vh, points[i], points[(i + 1) % points.Count], outlineWidth, outlineColor);
            }
        }

        // =====================
        // 汎用：多角形アウトライン描画
        // =====================
        private void DrawPolygonOutline(VertexHelper vh, Vector2 center, float r, int sides, Color col, float lineWidth)
        {
            List<Vector2> pts = new List<Vector2>();
            for (int i = 0; i < sides; i++)
            {
                float angle = _startAngle + (2f * Mathf.PI * i / sides);
                pts.Add(center + new Vector2(Mathf.Cos(angle), Mathf.Sin(angle)) * r);
            }
            for (int i = 0; i < pts.Count; i++)
            {
                DrawLine(vh, pts[i], pts[(i + 1) % pts.Count], lineWidth, col);
            }
        }

        // =====================
        // 汎用：太さのある線描画
        // =====================
        private void DrawLine(VertexHelper vh, Vector2 a, Vector2 b, float width, Color col)
        {
            Vector2 dir = (b - a).normalized;
            Vector2 perp = new Vector2(-dir.y, dir.x) * (width * 0.5f);

            int idx = vh.currentVertCount;
            UIVertex v0 = UIVertex.simpleVert; v0.position = a - perp; v0.color = col; vh.AddVert(v0);
            UIVertex v1 = UIVertex.simpleVert; v1.position = a + perp; v1.color = col; vh.AddVert(v1);
            UIVertex v2 = UIVertex.simpleVert; v2.position = b + perp; v2.color = col; vh.AddVert(v2);
            UIVertex v3 = UIVertex.simpleVert; v3.position = b - perp; v3.color = col; vh.AddVert(v3);

            vh.AddTriangle(idx, idx + 1, idx + 2);
            vh.AddTriangle(idx, idx + 2, idx + 3);
        }

        // =====================
        // ヘルパー
        // =====================
        private float GetCurrentValue(int index)
        {
            if (index < _currentValues.Count) return _currentValues[index];
            if (index < values.Count) return Mathf.Clamp01(values[index]);
            return 0f;
        }

#if UNITY_EDITOR
        protected override void OnValidate()
        {
            base.OnValidate();
            SyncValueCount();
            InitializeValues();
            SetVerticesDirty();
        }
#endif
    }
}
            """
            
            f.write(code)
            
    if not os.path.exists(RADAR_CHART_GENERATOR_RADARCHARTCONTROLLER_CS):
        with open(RADAR_CHART_GENERATOR_RADARCHARTCONTROLLER_CS, 'w', encoding='utf-8') as f:
            code = """
            using System.Collections;
using System.Collections.Generic;
using UnityEngine;

namespace RadarChartGenerator
{
    /// <summary>
    /// ゲーム実行中にレーダーチャートを動的に操作するコントローラー。
    /// RadarChart コンポーネントと同じ GameObject にアタッチしてください。
    /// </summary>
    [RequireComponent(typeof(RadarChart))]
    public class RadarChartController : MonoBehaviour
    {
        private RadarChart _chart;

        // =====================
        // デモ用設定
        // =====================
        [Header("デモ設定")]
        [Tooltip("起動時にデモアニメーションを再生する")]
        public bool playDemoOnStart = true;

        [Tooltip("デモのループ再生")]
        public bool loopDemo = true;

        [Tooltip("デモの各ステップ間隔（秒）")]
        public float demoInterval = 2f;

        [Header("プリセットデータ")]
        public List<ChartPreset> presets = new List<ChartPreset>
        {
            new ChartPreset { name = "バランス型",  values = new List<float>{ 0.7f,0.7f,0.7f,0.7f,0.7f } },
            new ChartPreset { name = "アタッカー",  values = new List<float>{ 1.0f,0.3f,0.8f,0.6f,0.4f } },
            new ChartPreset { name = "タンク",      values = new List<float>{ 0.4f,1.0f,0.3f,0.2f,0.9f } },
            new ChartPreset { name = "マジシャン",  values = new List<float>{ 0.3f,0.4f,0.5f,1.0f,0.6f } },
            new ChartPreset { name = "スピードスター",values= new List<float>{ 0.6f,0.4f,1.0f,0.5f,0.5f } },
        };

        // =====================
        // 初期化
        // =====================
        private void Start()
        {
            _chart = GetComponent<RadarChart>();
            if (playDemoOnStart)
                StartCoroutine(DemoCoroutine());
        }

        // =====================
        // デモコルーチン
        // =====================
        private IEnumerator DemoCoroutine()
        {
            int presetIndex = 0;
            do
            {
                foreach (var preset in presets)
                {
                    ApplyPreset(preset);
                    yield return new WaitForSeconds(demoInterval);
                    presetIndex++;
                }
            } while (loopDemo);
        }

        // =====================
        // 公開API
        // =====================
        /// <summary>プリセットを名前で適用</summary>
        public void ApplyPresetByName(string presetName)
        {
            var preset = presets.Find(p => p.name == presetName);
            if (preset != null) ApplyPreset(preset);
            else Debug.LogWarning($"[RadarChartController] プリセット '{presetName}' が見つかりません");
        }

        /// <summary>プリセットをインデックスで適用</summary>
        public void ApplyPresetByIndex(int index)
        {
            if (index >= 0 && index < presets.Count) ApplyPreset(presets[index]);
        }

        /// <summary>プリセットを適用</summary>
        public void ApplyPreset(ChartPreset preset)
        {
            if (_chart == null) return;
            _chart.SetAllValues(preset.values);
        }

        /// <summary>個別頂点の値を設定（0.0〜1.0）</summary>
        public void SetValue(int index, float value)
        {
            _chart?.SetValue(index, value);
        }

        /// <summary>全頂点の値をランダムに設定</summary>
        public void RandomizeValues()
        {
            if (_chart == null) return;
            var vals = new List<float>();
            for (int i = 0; i < _chart.vertexCount; i++)
                vals.Add(Random.Range(0.2f, 1f));
            _chart.SetAllValues(vals);
        }

        /// <summary>頂点数を変更（3〜12）</summary>
        public void SetVertexCount(int count)
        {
            _chart?.SetVertexCount(count);
        }

        /// <summary>全値を指定値に設定（0.0〜1.0）</summary>
        public void SetAllToValue(float value)
        {
            if (_chart == null) return;
            var vals = new List<float>();
            for (int i = 0; i < _chart.vertexCount; i++) vals.Add(value);
            _chart.SetAllValues(vals);
        }

        /// <summary>塗りつぶしモードを切り替え</summary>
        public void CycleFillMode()
        {
            if (_chart == null) return;
            int next = ((int)_chart.fillMode + 1) % 3;
            _chart.fillMode = (RadarChart.FillMode)next;
            _chart.SetVerticesDirty();
        }
    }

    // =====================
    // プリセットデータクラス
    // =====================
    [System.Serializable]
    public class ChartPreset
    {
        public string name;
        public List<float> values = new List<float>();
    }
}
            """
            f.write(code)
            
    if not os.path.exists( RADAR_CHART_GENERATOR_RADERCHARTGENERATORWINDOW_CS):
        with open(RADAR_CHART_GENERATOR_RADERCHARTGENERATORWINDOW_CS, 'w', encoding='utf-8') as f:
            code = """
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using UnityEditor;

namespace RadarChartGenerator
{
    /// <summary>
    /// レーダーチャートジェネレーター — Unityエディタ拡張GUIウィンドウ
    /// メニュー: Tools > Radar Chart Generator
    /// </summary>
    public class RadarChartGeneratorWindow : EditorWindow
    {
        // =====================
        // GUIステート
        // =====================
        private int _vertexCount = 5;
        private int _divisions = 5;
        private float _radius = 180f;

        private RadarChart.FillMode _fillMode = RadarChart.FillMode.SingleColor;
        private Color _fillColor = new Color(0.2f, 0.5f, 1f, 0.4f);
        private Gradient _fillGradient = new Gradient();
        private List<Color> _vertexColors = new List<Color>();
        private int _gradientSteps = 16;

        private bool _showOutline = true;
        private Color _outlineColor = new Color(0.2f, 0.5f, 1f, 1f);
        private float _outlineWidth = 2f;

        private bool _showGrid = true;
        private Color _gridColor = new Color(0.5f, 0.5f, 0.5f, 0.4f);
        private float _gridLineWidth = 1f;

        private bool _showAxes = true;
        private Color _axisColor = new Color(0.5f, 0.5f, 0.5f, 0.5f);
        private float _axisLineWidth = 1f;

        private bool _animateChanges = true;
        private float _animationSpeed = 3f;

        private List<float> _values = new List<float> { 0.8f, 0.6f, 0.9f, 0.5f, 0.7f };
        private List<string> _labels = new List<string> { "攻撃", "防御", "速度", "魔法", "体力" };

        private Vector2 _scrollPos;
        private bool _foldBasic = true;
        private bool _foldFill = true;
        private bool _foldOutline = true;
        private bool _foldGrid = true;
        private bool _foldValues = true;
        private bool _foldAnim = true;

        private SerializedObject _gradientSO;
        private GradientWrapper _gradientWrapper;

        // =====================
        // メニュー登録
        // =====================
        [MenuItem("Tools/Radar Chart Generator")]
        public static void Open()
        {
            var win = GetWindow<RadarChartGeneratorWindow>("Radar Chart Generator");
            win.minSize = new Vector2(400, 600);
            win.Show();
        }

        // =====================
        // 初期化
        // =====================
        private void OnEnable()
        {
            InitGradient();
            SyncListSizes();

            _gradientWrapper = ScriptableObject.CreateInstance<GradientWrapper>();
            _gradientWrapper.gradient = _fillGradient;
            _gradientSO = new SerializedObject(_gradientWrapper);
        }

        private void OnDisable()
        {
            if (_gradientWrapper != null)
                DestroyImmediate(_gradientWrapper);
        }

        private void InitGradient()
        {
            _fillGradient = new Gradient();
            _fillGradient.SetKeys(
                new GradientColorKey[]
                {
                    new GradientColorKey(new Color(0.2f, 0.5f, 1f), 0f),
                    new GradientColorKey(new Color(0.5f, 0.8f, 1f), 1f)
                },
                new GradientAlphaKey[]
                {
                    new GradientAlphaKey(0.8f, 0f),
                    new GradientAlphaKey(0.2f, 1f)
                }
            );
        }

        private void SyncListSizes()
        {
            while (_values.Count < _vertexCount) _values.Add(0.5f);
            while (_values.Count > _vertexCount) _values.RemoveAt(_values.Count - 1);

            while (_labels.Count < _vertexCount) _labels.Add("項目 " + (_labels.Count + 1));
            while (_labels.Count > _vertexCount) _labels.RemoveAt(_labels.Count - 1);

            while (_vertexColors.Count < _vertexCount) _vertexColors.Add(Random.ColorHSV(0f, 1f, 0.5f, 1f, 0.7f, 1f, 0.7f, 0.9f));
            while (_vertexColors.Count > _vertexCount) _vertexColors.RemoveAt(_vertexColors.Count - 1);
        }

        // =====================
        // GUI描画
        // =====================
        private void OnGUI()
        {
            DrawHeader();
            _scrollPos = EditorGUILayout.BeginScrollView(_scrollPos);

            DrawBasicSection();
            DrawFillSection();
            DrawOutlineSection();
            DrawGridSection();
            DrawValuesSection();
            DrawAnimSection();
            DrawActionButtons();

            EditorGUILayout.EndScrollView();
        }

        // =====================
        // ヘッダー
        // =====================
        private void DrawHeader()
        {
            var headerStyle = new GUIStyle(EditorStyles.boldLabel)
            {
                fontSize = 16,
                alignment = TextAnchor.MiddleCenter,
                normal = { textColor = new Color(0.4f, 0.8f, 1f) }
            };
            EditorGUILayout.Space(8);
            EditorGUILayout.LabelField("◆ Radar Chart Generator", headerStyle, GUILayout.Height(28));
            DrawSeparator();
        }

        // =====================
        // 基本設定セクション
        // =====================
        private void DrawBasicSection()
        {
            _foldBasic = DrawFoldout("基本設定", _foldBasic);
            if (!_foldBasic) return;
            EditorGUI.indentLevel++;

            int newVertex = EditorGUILayout.IntSlider("頂点数", _vertexCount, 3, 12);
            if (newVertex != _vertexCount)
            {
                _vertexCount = newVertex;
                SyncListSizes();
            }

            _divisions = EditorGUILayout.IntSlider("分割数（同心リング）", _divisions, 1, 10);
            _radius = EditorGUILayout.Slider("半径", _radius, 50f, 400f);

            EditorGUI.indentLevel--;
            DrawSeparator();
        }

        // =====================
        // 塗りつぶしセクション
        // =====================
        private void DrawFillSection()
        {
            _foldFill = DrawFoldout("塗りつぶし設定", _foldFill);
            if (!_foldFill) return;
            EditorGUI.indentLevel++;

            _fillMode = (RadarChart.FillMode)EditorGUILayout.EnumPopup("塗りつぶしモード", _fillMode);

            switch (_fillMode)
            {
                case RadarChart.FillMode.SingleColor:
                    _fillColor = EditorGUILayout.ColorField("塗りつぶし色", _fillColor);
                    break;

                case RadarChart.FillMode.RadialGradient:
                    EditorGUILayout.LabelField("グラデーション（内側 → 外側）", EditorStyles.miniLabel);

                    _gradientSO.Update();
                    var gradProp = _gradientSO.FindProperty("gradient");
                    EditorGUILayout.PropertyField(gradProp, new GUIContent("グラデーション"));
                    if (_gradientSO.ApplyModifiedProperties())
                    {
                        _fillGradient = _gradientWrapper.gradient;
                    }

                    _gradientSteps = EditorGUILayout.IntSlider("グラデーション精度", _gradientSteps, 2, 32);
                    break;

                case RadarChart.FillMode.VertexColor:
                    EditorGUILayout.LabelField("各頂点の色", EditorStyles.miniLabel);
                    for (int i = 0; i < _vertexCount; i++)
                    {
                        string lbl = (i < _labels.Count) ? _labels[i] : "頂点 " + (i + 1);
                        _vertexColors[i] = EditorGUILayout.ColorField($"  頂点 {i + 1}（{lbl}）", _vertexColors[i]);
                    }
                    break;
            }

            EditorGUI.indentLevel--;
            DrawSeparator();
        }

        // =====================
        // アウトラインセクション
        // =====================
        private void DrawOutlineSection()
        {
            _foldOutline = DrawFoldout("アウトライン設定", _foldOutline);
            if (!_foldOutline) return;
            EditorGUI.indentLevel++;

            _showOutline = EditorGUILayout.Toggle("アウトライン表示", _showOutline);
            if (_showOutline)
            {
                _outlineColor = EditorGUILayout.ColorField("アウトラインの色", _outlineColor);
                _outlineWidth = EditorGUILayout.Slider("アウトラインの太さ", _outlineWidth, 0.5f, 8f);
            }

            EditorGUI.indentLevel--;
            DrawSeparator();
        }

        // =====================
        // グリッドセクション
        // =====================
        private void DrawGridSection()
        {
            _foldGrid = DrawFoldout("グリッド／軸線設定", _foldGrid);
            if (!_foldGrid) return;
            EditorGUI.indentLevel++;

            _showGrid = EditorGUILayout.Toggle("グリッド表示", _showGrid);
            if (_showGrid)
            {
                _gridColor = EditorGUILayout.ColorField("グリッド色", _gridColor);
                _gridLineWidth = EditorGUILayout.Slider("グリッド線の太さ", _gridLineWidth, 0.5f, 4f);
            }

            EditorGUILayout.Space(4);

            _showAxes = EditorGUILayout.Toggle("軸線表示", _showAxes);
            if (_showAxes)
            {
                _axisColor = EditorGUILayout.ColorField("軸線色", _axisColor);
                _axisLineWidth = EditorGUILayout.Slider("軸線の太さ", _axisLineWidth, 0.5f, 4f);
            }

            EditorGUI.indentLevel--;
            DrawSeparator();
        }

        // =====================
        // 頂点値セクション
        // =====================
        private void DrawValuesSection()
        {
            _foldValues = DrawFoldout("頂点データ設定", _foldValues);
            if (!_foldValues) return;
            EditorGUI.indentLevel++;

            // ランダム生成ボタン
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("ランダム生成", GUILayout.Width(100)))
                {
                    for (int i = 0; i < _values.Count; i++) _values[i] = Random.Range(0.2f, 1f);
                }
                if (GUILayout.Button("全て1.0に", GUILayout.Width(90)))
                {
                    for (int i = 0; i < _values.Count; i++) _values[i] = 1f;
                }
                if (GUILayout.Button("全て0.5に", GUILayout.Width(90)))
                {
                    for (int i = 0; i < _values.Count; i++) _values[i] = 0.5f;
                }
            }

            EditorGUILayout.Space(4);
            for (int i = 0; i < _vertexCount; i++)
            {
                using (new EditorGUILayout.HorizontalScope())
                {
                    // ラベル編集
                    _labels[i] = EditorGUILayout.TextField(_labels[i], GUILayout.Width(80));
                    _values[i] = EditorGUILayout.Slider(_values[i], 0f, 1f);
                    EditorGUILayout.LabelField($"{_values[i]:F2}", GUILayout.Width(36));
                }
            }

            EditorGUI.indentLevel--;
            DrawSeparator();
        }

        // =====================
        // アニメーションセクション
        // =====================
        private void DrawAnimSection()
        {
            _foldAnim = DrawFoldout("アニメーション設定", _foldAnim);
            if (!_foldAnim) return;
            EditorGUI.indentLevel++;

            _animateChanges = EditorGUILayout.Toggle("値変化アニメーション", _animateChanges);
            if (_animateChanges)
                _animationSpeed = EditorGUILayout.Slider("アニメーション速度", _animationSpeed, 0.5f, 10f);

            EditorGUI.indentLevel--;
            DrawSeparator();
        }

        // =====================
        // アクションボタン
        // =====================
        private void DrawActionButtons()
        {
            EditorGUILayout.Space(8);

            var btnStyle = new GUIStyle(GUI.skin.button)
            {
                fontSize = 13,
                fontStyle = FontStyle.Bold,
                fixedHeight = 38
            };

            // メイン生成ボタン
            GUI.backgroundColor = new Color(0.3f, 0.8f, 0.4f);
            if (GUILayout.Button("▶  チャートを生成（Canvas に配置）", btnStyle))
                CreateRadarChart();
            GUI.backgroundColor = Color.white;

            EditorGUILayout.Space(4);

            // 選択中のチャートに設定反映
            GUI.backgroundColor = new Color(0.3f, 0.6f, 1f);
            if (GUILayout.Button("↺  選択中のチャートに設定を反映", btnStyle))
                ApplyToSelected();
            GUI.backgroundColor = Color.white;

            EditorGUILayout.Space(4);

            // ラベル付きで生成
            GUI.backgroundColor = new Color(0.9f, 0.7f, 0.2f);
            if (GUILayout.Button("★  ラベル付きチャートを生成", btnStyle))
                CreateRadarChartWithLabels();
            GUI.backgroundColor = Color.white;

            EditorGUILayout.Space(8);
        }

        // =====================
        // チャート生成
        // =====================
        private void CreateRadarChart()
        {
            // Canvas確保
            var canvas = EnsureCanvas();

            // 親パネル
            var chartObj = new GameObject("RadarChart");
            chartObj.transform.SetParent(canvas.transform, false);

            var rt = chartObj.AddComponent<RectTransform>();
            rt.sizeDelta = new Vector2(_radius * 2.2f, _radius * 2.2f);
            rt.anchoredPosition = Vector2.zero;

            // RadarChartコンポーネント追加
            var chart = chartObj.AddComponent<RadarChart>();
            ApplySettings(chart);

            Undo.RegisterCreatedObjectUndo(chartObj, "Create Radar Chart");
            Selection.activeGameObject = chartObj;
            Debug.Log($"[RadarChart] 生成完了: {chartObj.name}");
        }

        private void CreateRadarChartWithLabels()
        {
            var canvas = EnsureCanvas();

            // ルートオブジェクト
            var rootObj = new GameObject("RadarChart_WithLabels");
            rootObj.transform.SetParent(canvas.transform, false);
            var rootRt = rootObj.AddComponent<RectTransform>();
            rootRt.sizeDelta = new Vector2(_radius * 2.8f, _radius * 2.8f);
            rootRt.anchoredPosition = Vector2.zero;

            // チャート本体
            var chartObj = new GameObject("Chart");
            chartObj.transform.SetParent(rootObj.transform, false);
            var chartRt = chartObj.AddComponent<RectTransform>();
            chartRt.sizeDelta = new Vector2(_radius * 2.2f, _radius * 2.2f);
            chartRt.anchoredPosition = Vector2.zero;
            var chart = chartObj.AddComponent<RadarChart>();
            ApplySettings(chart);

            // ラベルオブジェクト
            for (int i = 0; i < _vertexCount; i++)
            {
                float angle = -Mathf.PI / 2f + (2f * Mathf.PI * i / _vertexCount);
                float labelRadius = _radius * 1.25f;
                Vector2 pos = new Vector2(Mathf.Cos(angle), Mathf.Sin(angle)) * labelRadius;

                var labelObj = new GameObject($"Label_{i}_{_labels[i]}");
                labelObj.transform.SetParent(rootObj.transform, false);
                var labelRt = labelObj.AddComponent<RectTransform>();
                labelRt.sizeDelta = new Vector2(100f, 30f);
                labelRt.anchoredPosition = pos;

                var tmp = labelObj.AddComponent<Text>();
                tmp.text = _labels[i];
                tmp.fontSize = 14;
                tmp.alignment = TextAnchor.MiddleCenter;
                tmp.color = Color.white;
                var font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
                tmp.font = font;
            }

            Undo.RegisterCreatedObjectUndo(rootObj, "Create Radar Chart With Labels");
            Selection.activeGameObject = rootObj;
            Debug.Log($"[RadarChart] ラベル付き生成完了: {rootObj.name}");
        }

        private void ApplyToSelected()
        {
            var chart = Selection.activeGameObject?.GetComponent<RadarChart>();
            if (chart == null)
            {
                EditorUtility.DisplayDialog("エラー", "RadarChart コンポーネントを持つオブジェクトを選択してください。", "OK");
                return;
            }
            Undo.RecordObject(chart, "Apply Radar Chart Settings");
            ApplySettings(chart);
            EditorUtility.SetDirty(chart);
            Debug.Log($"[RadarChart] 設定を反映しました: {chart.gameObject.name}");
        }

        private void ApplySettings(RadarChart chart)
        {
            chart.vertexCount = _vertexCount;
            chart.divisions = _divisions;
            chart.radius = _radius;

            chart.fillMode = _fillMode;
            chart.fillColor = _fillColor;
            chart.fillGradient = CloneGradient(_fillGradient);
            chart.vertexColors = new List<Color>(_vertexColors);
            chart.gradientSteps = _gradientSteps;

            chart.showOutline = _showOutline;
            chart.outlineColor = _outlineColor;
            chart.outlineWidth = _outlineWidth;

            chart.showGrid = _showGrid;
            chart.gridColor = _gridColor;
            chart.gridLineWidth = _gridLineWidth;

            chart.showAxes = _showAxes;
            chart.axisColor = _axisColor;
            chart.axisLineWidth = _axisLineWidth;

            chart.animateChanges = _animateChanges;
            chart.animationSpeed = _animationSpeed;

            chart.values = new List<float>(_values);

            EditorUtility.SetDirty(chart);
        }

        // =====================
        // ユーティリティ
        // =====================
        private Canvas EnsureCanvas()
        {
            var canvas = GameObject.FindAnyObjectByType<Canvas>();
            if (canvas != null) return canvas;

            var canvasObj = new GameObject("Canvas");
            canvas = canvasObj.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvasObj.AddComponent<CanvasScaler>();
            canvasObj.AddComponent<GraphicRaycaster>();
            Undo.RegisterCreatedObjectUndo(canvasObj, "Create Canvas");
            Debug.Log("[RadarChart] Canvasを自動生成しました");
            return canvas;
        }

        private Gradient CloneGradient(Gradient src)
        {
            var g = new Gradient();
            g.SetKeys(src.colorKeys, src.alphaKeys);
            g.mode = src.mode;
            return g;
        }

        private bool DrawFoldout(string label, bool state)
        {
            var style = new GUIStyle(EditorStyles.foldout)
            {
                fontStyle = FontStyle.Bold,
                fontSize = 12
            };
            bool result = EditorGUILayout.Foldout(state, " " + label, true, style);
            return result;
        }

        private void DrawSeparator()
        {
            EditorGUILayout.Space(4);
            var rect = EditorGUILayout.GetControlRect(false, 1f);
            EditorGUI.DrawRect(rect, new Color(0.4f, 0.4f, 0.4f, 0.5f));
            EditorGUILayout.Space(4);
        }
    }

    // =====================
    // Gradient をSerializedObjectで扱うためのWrapper
    // =====================
    internal class GradientWrapper : ScriptableObject
    {
        public Gradient gradient = new Gradient();
    }
}
            
            """
            
            f.write(code)        
        