import json
import math
import os
import socket
import struct
import sys
import tkinter as tk
from tkinter import filedialog
import shutil
import uuid
# 実行可能ファイルのディレクトリを取得（PyInstaller対応）
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "data"))
ADDRESSABLE_LIB_DIR = os.path.join(DATA_DIR,"AdressableSupportLib")
ADDRESSABLE_EDITOR_DIR = os.path.join(ADDRESSABLE_LIB_DIR, "Editor")


    

def generate_file(path,code_str):
    if not os.path.exists(path):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(code_str)
def generate_base():      

    if not os.path.exists(ADDRESSABLE_LIB_DIR):
        os.mkdir(ADDRESSABLE_LIB_DIR)
    if not os.path.exists(ADDRESSABLE_EDITOR_DIR):
        os.mkdir(ADDRESSABLE_EDITOR_DIR)
    code_str = """

using Cysharp.Threading.Tasks;
using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.AddressableAssets;
using UnityEngine.ResourceManagement.AsyncOperations;
using UnityEngine.SceneManagement;

namespace AddressableSystem
{
    /// <summary>
    /// 型 T を受け取り、Load 時に Action<T> を呼ぶシンプル実装。
    /// BaseAddressableData は管理用で、ここに Load メソッドを公開する（override ではない）。
    /// </summary>
    public class AddressableData<T> : BaseAddressableData where T : UnityEngine.Object
    {
        private bool isInstantiated;
        private AsyncOperationHandle<T> handle;
        private AsyncOperationHandle<IList<T>> arrayHandle;

        protected T typedAddressableObject;
        protected T[] typedAddressableArray;


        public T GetAddressableObjectResult()
        {
            return typedAddressableObject;
        }
        public T[] GetAddressableObjectArrayResult()
        {
            return typedAddressableArray;
        }

        public AddressableData(GroupCategory group, AssetCategory category, string path,Scene? sceneLink = null)
            : base(group, category,path,sceneLink)
        {
        }

        /// <summary>
        /// 単体ロード。onSuccess に読み込まれた T を渡す（ラムダの引数は T 型）。
        /// </summary>
        public async UniTask LoadAsync( Action<T> onSuccess = null, Action<Exception> onError = null)
        {
            if (isLoaded || isSetup || string.IsNullOrEmpty(path))
            {
                Debug.LogWarning($"Cannot load: Already loaded/setup or invalid path: {path}");
                onError?.Invoke(new InvalidOperationException("Invalid load state or path"));
                return;
            }
            if (isCopy)
            {
                var data = AddressableDataCore.Instance.Find(groupCategory, assetCategory, this.path) as AddressableData<T>;
                if (data != null)
                {
                    while (data.IsLoadedAndSetup == false)
                    {
                        await UniTask.Yield(PlayerLoopTiming.Update);
                    }
                    onSuccess?.Invoke(data.GetAddressableObjectResult());
                    isLoaded = true;
                    isSetup = true;
                    return;

                }
            }

            isLoaded = true;
            try
            {
                handle = Addressables.LoadAssetAsync<T>(path);
                typedAddressableObject = await handle.ToUniTask();
                addressableObject = typedAddressableObject;
                await UniTask.Yield(PlayerLoopTiming.Update);

                if (handle.Status == AsyncOperationStatus.Succeeded)
                {
                    typedAddressableArray = new T[] { typedAddressableObject };
                    addressableArray = new UnityEngine.Object[] { addressableObject };
                    isSetup = true;
                    onSuccess?.Invoke(typedAddressableObject);
                }
                else
                {
                    Debug.LogError($"Failed to load asset at {path}: {handle.OperationException}");
                    isLoaded = false;
                    onError?.Invoke(handle.OperationException);
                }
            }
            catch (Exception ex)
            {
                Debug.LogError($"Exception loading asset at {path}: {ex.Message}");
                isLoaded = false;
                onError?.Invoke(ex);
            }
        }

        /// <summary>
        /// 配列ロード。onSuccess に IList<T> を渡す（ラムダの引数は IList<T>）。
        /// </summary>
        public async UniTask LoadArrayAsync( Action<IList<T>> onSuccess = null, Action<Exception> onError = null)
        {
            if (isLoaded || isSetup || string.IsNullOrEmpty(path))
            {
                Debug.LogWarning($"Cannot load array: Already loaded/setup or invalid path: {path}");
                onError?.Invoke(new InvalidOperationException("Invalid load state or path"));
                return;
            }
            if (isCopy)
            {
                var data = AddressableDataCore.Instance.Find(groupCategory, assetCategory, this.path) as AddressableData<T>;
                if (data != null)
                {
                    while (data.IsLoadedAndSetup == false)
                    {
                        await UniTask.Yield(PlayerLoopTiming.Update);
                    }
                    onSuccess?.Invoke(data.GetAddressableObjectArrayResult());
                    isLoaded = isSetup = true;
                    return;

                }
            }
            isLoaded = true;
            try
            {
                arrayHandle = Addressables.LoadAssetAsync<IList<T>>(path);
                var result = await arrayHandle.ToUniTask();
                await UniTask.Yield(PlayerLoopTiming.Update);

                if (arrayHandle.Status == AsyncOperationStatus.Succeeded)
                {
                    int cnt = result?.Count ?? 0;
                    typedAddressableArray = new T[cnt];
                    addressableArray = new UnityEngine.Object[cnt];

                    for (int i = 0; i < cnt; i++)
                    {
                        typedAddressableArray[i] = result[i];
                        addressableArray[i] = result[i];
                    }

                    typedAddressableObject = typedAddressableArray.Length > 0 ? typedAddressableArray[0] : null;
                    addressableObject = typedAddressableObject;
                    isSetup = true;
                    isArray = true;

                    onSuccess?.Invoke(result);
                }
                else
                {
                    Debug.LogError($"Failed to load array at {path}: {arrayHandle.OperationException}");
                    isLoaded = false;
                    onError?.Invoke(arrayHandle.OperationException);
                }
            }
            catch (Exception ex)
            {
                Debug.LogError($"Exception loading array at {path}: {ex.Message}");
                isLoaded = false;
                onError?.Invoke(ex);
            }
        }

        /// <summary>
        /// GameObject の場合にインスタンス化して返す（内部で T を参照）
        /// </summary>
        public GameObject Instantiate(string name = null)
        {
            if (!isSetup || typedAddressableObject == null || typedAddressableObject is not GameObject || isInstantiated)
            {
                Debug.LogWarning("Cannot instantiate: Asset not loaded, not a GameObject, or already instantiated.");
                return null;
            }

            if (isCopy)
            {
                var data = AddressableDataCore.Instance.Find(groupCategory, assetCategory, this.path) as AddressableData<T>;
                if (data != null)
                {
                    EnableAutoRelease();
                    return data.Instantiate(name);
                }
            }

                    isInstantiated = true;
            EnableAutoRelease();
            var instantiated = GameObject.Instantiate(typedAddressableObject as GameObject);
            if (!string.IsNullOrEmpty(name)) instantiated.name = name;
            return instantiated;
        }

        /// <summary>
        /// Release 実装
        /// </summary>
        public override void Release()
        {
            if(isCopy)
            {
                var data = AddressableDataCore.Instance.Find(groupCategory, assetCategory, this.path) as AddressableData<T>;
                if (data != null)
                {
                    data.Release();
                }
                // 元データへ委譲した後も、このコピー自身が isSetup/isLoaded = true のまま
                // 古い参照を保持し続けてしまうため、コピー自身の状態も必ずリセットする。
                addressableObject = null;
                addressableArray = null;
                typedAddressableObject = null;
                typedAddressableArray = null;
                isSetup = false;
                isLoaded = false;
                isInstantiated = false;
                return;
            }
            if (!IsLoadedAndSetup) return;

            if (!isArray && typedAddressableObject != null && handle.IsValid())
            {
                Addressables.Release(handle);
            }
            else if (isArray && typedAddressableArray != null && arrayHandle.IsValid())
            {
                if (typeof(T) == typeof(GameObject))
                {
                    foreach (var obj in addressableArray)
                    {
                        if (obj is GameObject gameObject)
                        {
                            Addressables.ReleaseInstance(gameObject);
                        }
                    }
                }
                Addressables.Release(arrayHandle);
            }

            // ユーザの要望どおり：戻り値を無視して呼ぶだけ（環境によっては void 扱い）
            if (addressableObject != null)
            {
                try
                {
                    Addressables.ClearDependencyCacheAsync(addressableObject.name);
                }
                catch (Exception ex)
                {
                    Debug.LogWarning($"Exception while calling ClearDependencyCacheAsync for {addressableObject.name}: {ex.Message}");
                }
            }

            addressableObject = null;
            addressableArray = null;
            typedAddressableObject = null;
            typedAddressableArray = null;
            isSetup = false;
            isLoaded = false;
            isInstantiated = false;

            Resources.UnloadUnusedAssets();
        }
    }
}


    """

    generate_file(os.path.join(ADDRESSABLE_LIB_DIR,"AddressableData.cs"),code_str)

    code_str = """

using System;
using System.Collections.Generic;
using System.Text;
using UnityEngine;
using System.Linq;
namespace AddressableSystem
{
    /// <summary>
    /// Defines categories for addressable assets.
    /// </summary>
    public enum AssetCategory
    {
        Prefab,
        Texture,
        Sprite,
        Audio,
        Material,
        UI,
        Other
    }

    /// <summary>
    /// Defines groups for addressable assets (e.g., game modes or scenes).
    /// </summary>
    public enum GroupCategory
    {
        Title,
        Game,
        Exit,
        Menu,
        Other
    }

    /// <summary>
    /// Interface for addressable data container.
    /// </summary>
    public interface IAddressableDataContainer
    {
        int Count { get; }
        int GetGroupCount(GroupCategory group);
        int GetCategoryCount(GroupCategory group, AssetCategory category);
        void Add(GroupCategory group, AssetCategory category, BaseAddressableData data);
        void Remove(GroupCategory group, AssetCategory category, BaseAddressableData data);
        BaseAddressableData Find(GroupCategory group, AssetCategory category, int index);
        BaseAddressableData Find(GroupCategory group, AssetCategory category, string path);
        BaseAddressableData Find(BaseAddressableData data);
        void AutoRelease();
        void ReleaseGroup(GroupCategory group);
        void ReleaseCategory(GroupCategory group, AssetCategory category);
        void ReleaseAssetCategory(AssetCategory asset);
        string GetGroupStats();

        /// <summary>
        /// Editor向け: 現在追跡中の全エントリのスナップショットを返す（Runtime専用ウィンドウ表示用）。
        /// </summary>
        List<BaseAddressableData> GetAllEntries();
        List<GroupCategory> GetActiveGroups();
        List<AssetCategory> GetActiveCategories(GroupCategory group);
    }

    /// <summary>
    /// Manages a collection of BaseAddressableData instances, organized by group and category.
    /// </summary>
    public class AddressableDataContainer : IAddressableDataContainer
    {
        private readonly Dictionary<GroupCategory, Dictionary<AssetCategory, List<BaseAddressableData>>> groupDataMap =
            new Dictionary<GroupCategory, Dictionary<AssetCategory, List<BaseAddressableData>>>();
            
        public Dictionary<GroupCategory, Dictionary<AssetCategory, List<BaseAddressableData>>> GetAllEntries()
        {
            return groupDataMap;
        }

        public int Count
        {
            get
            {
                int total = 0;
                foreach (var group in groupDataMap.Values)
                {
                    foreach (var list in group.Values)
                    {
                        total += list?.Count ?? 0;
                    }
                }
                return total;
            }
        }

        public int GetGroupCount(GroupCategory group)
        {
            if (groupDataMap.TryGetValue(group, out var categoryMap))
            {
                int total = 0;
                foreach (var list in categoryMap.Values)
                {
                    total += list?.Count ?? 0;
                }
                return total;
            }
            return 0;
        }

        public int GetCategoryCount(GroupCategory group, AssetCategory category)
        {
            if (groupDataMap.TryGetValue(group, out var categoryMap) &&
                categoryMap.TryGetValue(category, out var list))
            {
                return list?.Count ?? 0;
            }
            return 0;
        }

        public void Add(GroupCategory group, AssetCategory category, BaseAddressableData data)
        {
            if (data == null)
            {
                Debug.LogWarning("Attempted to add null data to AddressableDataContainer.");
                return;
            }
            if (!Enum.IsDefined(typeof(GroupCategory), group))
            {
                Debug.LogError($"Invalid group: {group}");
                throw new ArgumentException("Invalid GroupCategory.");
            }
            if (!Enum.IsDefined(typeof(AssetCategory), category))
            {
                Debug.LogError($"Invalid category: {category}");
                throw new ArgumentException("Invalid AssetCategory.");
            }

            if (!groupDataMap.TryGetValue(group, out var categoryMap))
            {
                categoryMap = new Dictionary<AssetCategory, List<BaseAddressableData>>();
                groupDataMap[group] = categoryMap;
            }
            if (!categoryMap.TryGetValue(category, out var list))
            {
                list = new List<BaseAddressableData>();
                categoryMap[category] = list;
            }
            if (Find(group, category, data.path) != null)
            {
                data.isCopy = true;
                return;
            }
            list.Add(data);
        }

        /// <summary>
        /// Single/SubGroup単位の解放時に、追跡リストから該当エントリのみを取り除く。
        /// isCopy（他インスタンスへのエイリアス）はそもそもリストに追加されていないため何もしない。
        /// </summary>
        public void Remove(GroupCategory group, AssetCategory category, BaseAddressableData data)
        {
            if (data == null || data.isCopy) return;
            if (!groupDataMap.TryGetValue(group, out var categoryMap)) return;
            if (!categoryMap.TryGetValue(category, out var list) || list == null) return;

            if (!list.Remove(data)) return; // 参照一致で削除。見つからなければ何もしない

            if (list.Count == 0)
            {
                categoryMap.Remove(category);
                if (categoryMap.Count == 0)
                {
                    groupDataMap.Remove(group);
                }
            }
        }

        public BaseAddressableData Find(GroupCategory group, AssetCategory category, int index)
        {
            if (!Enum.IsDefined(typeof(GroupCategory), group) || !Enum.IsDefined(typeof(AssetCategory), category))
            {
                Debug.LogWarning($"Invalid group {group} or category {category} for AddressableDataContainer.Find.");
                return null;
            }
            if (!groupDataMap.TryGetValue(group, out var categoryMap) ||
                !categoryMap.TryGetValue(category, out var list) || list == null || index < 0 || index >= list.Count)
            {
                Debug.LogWarning($"Invalid group {group}, category {category}, or index {index} for AddressableDataContainer.Find.");
                return null;
            }
            return list[index];
        }
        public BaseAddressableData Find(GroupCategory group, AssetCategory category, string path)
        {
            if (!Enum.IsDefined(typeof(GroupCategory), group) || !Enum.IsDefined(typeof(AssetCategory), category))
            {
                Debug.LogWarning($"Invalid group {group} or category {category} for AddressableDataContainer.Find.");
                return null;
            }
            if (!groupDataMap.TryGetValue(group, out var categoryMap) ||
                !categoryMap.TryGetValue(category, out var list) || list == null)
            {
                Debug.LogWarning($"Invalid group {group}, category {category}, or index {path} for AddressableDataContainer.Find.");
                return null;
            }
            return list.Find(data => data.groupCategory == group && data.assetCategory == category && data.path == path);
        }

        public BaseAddressableData Find(BaseAddressableData data)
        {
            if (data == null)
            {
                Debug.LogWarning("Attempted to find null data in AddressableDataContainer.");
                return null;
            }

            foreach (var categoryMap in groupDataMap.Values)
            {
                foreach (var list in categoryMap.Values)
                {
                    if (list != null)
                    {
                        var found = list.Find(item => item == data);
                        if (found != null)
                        {
                            return found;
                        }
                    }
                }
            }
            Debug.LogWarning("Data not found in AddressableDataContainer.");
            return null;
        }

        public void AutoRelease()
        {
            foreach (var groupKvp in groupDataMap)
            {
                var categoryMap = groupKvp.Value;
                foreach (var categoryKvp in categoryMap)
                {
                    var list = categoryKvp.Value;
                    if (list == null || list.Count == 0) continue;

                    for (int i = list.Count - 1; i >= 0; i--)
                    {
                        var data = list[i];
                        if (data.IsAutoRelease && data.IsLoadedAndSetup && data.GetAddressableObject() == null)
                        {
                            data.Release();
                            list.RemoveAt(i);
                        }
                    }

                    if (list.Count == 0)
                    {
                        categoryMap.Remove(categoryKvp.Key);
                    }
                    else
                    {
                        list.TrimExcess();
                    }
                }

                if (categoryMap.Count == 0)
                {
                    groupDataMap.Remove(groupKvp.Key);
                }
            }
        }

        public void ReleaseGroup(GroupCategory group)
        {
            if (!groupDataMap.TryGetValue(group, out var categoryMap) || categoryMap == null)
            {
                Debug.LogWarning($"No data found for group {group} in AddressableDataContainer.");
                return;
            }

            foreach (var list in categoryMap.Values)
            {
                foreach (var data in list)
                {
                    data.Release();
                }
                list.Clear();
            }
            categoryMap.Clear();
            groupDataMap.Remove(group);
        }

        public void ReleaseAssetCategory(AssetCategory asset)
        {
            var emptyGroups = new List<GroupCategory>();
            foreach (var groupKvp in groupDataMap)
            {
                var categoryMap = groupKvp.Value;
                if (!categoryMap.TryGetValue(asset, out var list) || list == null) continue;

                foreach (var data in list)
                {
                    data.Release();
                }
                list.Clear();
                categoryMap.Remove(asset);

                if (categoryMap.Count == 0)
                {
                    emptyGroups.Add(groupKvp.Key);
                }
            }

            foreach (var group in emptyGroups)
            {
                groupDataMap.Remove(group);
            }
        }

        public void ReleaseCategory(GroupCategory group, AssetCategory category)
        {
            if (!groupDataMap.TryGetValue(group, out var categoryMap) ||
                !categoryMap.TryGetValue(category, out var list) || list == null)
            {
                Debug.LogWarning($"No data found for group {group}, category {category} in AddressableDataContainer.");
                return;
            }

            foreach (var data in list)
            {
                data.Release();
            }
            list.Clear();
            categoryMap.Remove(category);
            if (categoryMap.Count == 0)
            {
                groupDataMap.Remove(group);
            }
        }

        public string GetGroupStats()
        {
            var stats = new StringBuilder("AddressableDataContainer Stats:");
            foreach (var groupKvp in groupDataMap)
            {
                stats.AppendLine($"Group: {groupKvp.Key}, Total Count: {GetGroupCount(groupKvp.Key)}");
                foreach (var categoryKvp in groupKvp.Value)
                {
                    stats.AppendLine($"  Category: {categoryKvp.Key}, Count: {categoryKvp.Value?.Count ?? 0}, Loaded: {categoryKvp.Value?.Count(d => d.IsLoadedAndSetup) ?? 0}");
                }
            }
            return stats.ToString();
        }

        /// <summary>
        /// Editor向け: 現在追跡中の全エントリのスナップショット（参照のコピー）を返す。
        /// 列挙中にコレクションが変更されても影響を受けないよう、必ず新しいListを返す。
        /// </summary>
        public List<BaseAddressableData> GetAllEntries()
        {
            var result = new List<BaseAddressableData>();
            foreach (var categoryMap in groupDataMap.Values)
            {
                foreach (var list in categoryMap.Values)
                {
                    if (list == null) continue;
                    result.AddRange(list);
                }
            }
            return result;
        }

        public List<GroupCategory> GetActiveGroups()
        {
            return groupDataMap.Keys.ToList();
        }

        public List<AssetCategory> GetActiveCategories(GroupCategory group)
        {
            if (groupDataMap.TryGetValue(group, out var categoryMap))
            {
                return categoryMap.Keys.ToList();
            }
            return new List<AssetCategory>();
        }
        
    }
}
    """
    generate_file(os.path.join(ADDRESSABLE_LIB_DIR,"AddressableDataContainer.cs"),code_str)

    code_str = """
using Cysharp.Threading.Tasks;
using System;
using System.Collections.Generic;
using System.Threading;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace AddressableSystem
{
    /// <summary>
    /// Central manager for addressable assets, implemented as a singleton.
    /// </summary>
    public class AddressableDataCore : MonoBehaviour
    {
        private static AddressableDataCore instance;
        [SerializeField] private AddressableDataContainer dataContainer = new AddressableDataContainer();
        private readonly Dictionary<int, Dictionary<GroupCategory, List<BaseAddressableData>>> sceneDataMap =
            new Dictionary<int, Dictionary<GroupCategory, List<BaseAddressableData>>>();
        private CancellationTokenSource cts = new CancellationTokenSource();

        public static AddressableDataCore Instance
        {
            get
            {
                if (instance == null)
                {
                    
                    var gameObject = new GameObject("AddressableDataCore");
                    instance = gameObject.AddComponent<AddressableDataCore>();
                    DontDestroyOnLoad(gameObject);
                }
                return instance;
            }
        }

        public AddressableDataContainer DataContainer => dataContainer;

        public static AddressableObject<T> CreateAddressable<T>(string path) where T : UnityEngine.Object
        {
            return new AddressableObject<T>(path);
        }

        public static AddressableObject<T> CreateAddressableLoad<T>(string path,Action<T> action) where T : UnityEngine.Object
        {
            var result = new AddressableObject<T>(path);
            result.LoadAsync(action).Forget();
            return result;
        }


        protected virtual void Awake()
        {
            if (instance == null)
            {
                instance = this;
                DontDestroyOnLoad(gameObject);
            }
            else if (instance != this)
            {
                Destroy(gameObject);
                return;
            }

            if (dataContainer == null)
            {
                dataContainer = new AddressableDataContainer();
            }

            SceneManager.sceneUnloaded += OnSceneUnloaded;
        }

        protected virtual void Start()
        {
            AutoReleaseRoutine(cts.Token).Forget();
        }

        protected virtual void OnDestroy()
        {
            cts.Cancel();
            cts.Dispose();
            SceneManager.sceneUnloaded -= OnSceneUnloaded;
            Resources.UnloadUnusedAssets();
            if (instance == this) instance = null;
        }

        private async UniTaskVoid AutoReleaseRoutine(CancellationToken token)
        {
            while (!token.IsCancellationRequested)
            {
                try
                {
                    dataContainer?.AutoRelease();
                    
                    await UniTask.Delay(1000, delayTiming: PlayerLoopTiming.Update, cancellationToken: token);
                }
                catch (OperationCanceledException) { }
                catch (Exception ex)
                {
                    Debug.LogError($"AutoRelease error: {ex.Message}");
                }
            }
        }

        private void OnSceneUnloaded(Scene scene)
        {
            if (sceneDataMap.TryGetValue(scene.buildIndex, out var groupMap))
            {
                foreach (var list in groupMap.Values)
                {
                    foreach (var data in list)
                    {
                        data.Release();
                    }
                    list.Clear();
                }
                groupMap.Clear();
                sceneDataMap.Remove(scene.buildIndex);
            }
        }

        /// <summary>
        /// Cancels the auto-release routine.
        /// </summary>
        public void CancelAutoRelease()
        {
            cts.Cancel();
            cts.Dispose();
            cts = new CancellationTokenSource();
        }

        /// <summary>
        /// Adds addressable data to the specified group and category.
        /// </summary>
        public void AddAddressableData(GroupCategory group, AssetCategory category, BaseAddressableData data, Scene? sceneLink = null)
        {
            if (data == null)
            {
                Debug.LogWarning("Attempted to add null data.");
                return;
            }
            if (!Enum.IsDefined(typeof(GroupCategory), group))
            {
                Debug.LogError($"Invalid group: {group}");
                throw new ArgumentException("Invalid GroupCategory.");
            }
            if (!Enum.IsDefined(typeof(AssetCategory), category))
            {
                Debug.LogError($"Invalid category: {category}");
                throw new ArgumentException("Invalid AssetCategory.");
            }

            data.SceneLink = sceneLink;
            if (sceneLink.HasValue)
            {
                if (!sceneDataMap.TryGetValue(sceneLink.Value.buildIndex, out var groupMap))
                {
                    groupMap = new Dictionary<GroupCategory, List<BaseAddressableData>>();
                    sceneDataMap[sceneLink.Value.buildIndex] = groupMap;
                }
                if (!groupMap.TryGetValue(group, out var list))
                {
                    list = new List<BaseAddressableData>();
                    groupMap[group] = list;
                }
                list.Add(data);
            }
            dataContainer?.Add(group, category, data);
        }

        /// <summary>
        /// Single/SubGroup単位の解放で使用。data自身が保持するgroupCategory/assetCategoryを使って
        /// 追跡リストから当該エントリのみを除去する（Group/Category単位の一括解放では使わないこと）。
        /// </summary>
        public void RemoveData(BaseAddressableData data)
        {
            if (data == null) return;
            dataContainer?.Remove(data.groupCategory, data.assetCategory, data);
        }

        /// <summary>
        /// Finds addressable data by index in the specified group and category.
        /// </summary>
        public BaseAddressableData Find(GroupCategory group, AssetCategory category, int index)
        {
            if (!Enum.IsDefined(typeof(GroupCategory), group) || !Enum.IsDefined(typeof(AssetCategory), category))
            {
                Debug.LogWarning($"Invalid group {group} or category {category}");
                return null;
            }
            return dataContainer?.Find(group, category, index);
        }

        /// <summary>
        /// Finds addressable data by index in the specified group and category.
        /// </summary>
        public BaseAddressableData Find(GroupCategory group, AssetCategory category, string path)
        {
            if (!Enum.IsDefined(typeof(GroupCategory), group) || !Enum.IsDefined(typeof(AssetCategory), category))
            {
                Debug.LogWarning($"Invalid group {group} or category {category}");
                return null;
            }
            return dataContainer?.Find(group, category, path);
        }

        /// <summary>
        /// Finds addressable data by reference across all groups and categories.
        /// </summary>
        public BaseAddressableData Find(BaseAddressableData data)
        {
            return dataContainer?.Find(data);
        }

        /// <summary>
        /// Releases all data in the specified group.
        /// </summary>
        public void ReleaseGroup(GroupCategory group)
        {
            dataContainer?.ReleaseGroup(group);
            Resources.UnloadUnusedAssets();
        }

        public void ReleaseAssetsAll(AssetCategory asset)
        {
            dataContainer?.ReleaseAssetCategory(asset);
        }

        /// <summary>
        /// Releases all data in the specified group and category.
        /// </summary>
        public void ReleaseCategory(GroupCategory group, AssetCategory category)
        {
            dataContainer?.ReleaseCategory(group, category);
            Resources.UnloadUnusedAssets();
        }

        /// <summary>
        /// Editor向け: AddressableManagerWindow が現在のロード状況を描画するために使用する。
        /// </summary>
        public List<BaseAddressableData> GetAllEntries()
        {
            return dataContainer?.GetAllEntries() ?? new List<BaseAddressableData>();
        }

        public List<GroupCategory> GetActiveGroups()
        {
            return dataContainer?.GetActiveGroups() ?? new List<GroupCategory>();
        }

        public List<AssetCategory> GetActiveCategories(GroupCategory group)
        {
            return dataContainer?.GetActiveCategories(group) ?? new List<AssetCategory>();
        }

        public string GetGroupStats()
        {
            return dataContainer?.GetGroupStats() ?? string.Empty;
        }
        
        public Dictionary<GroupCategory, Dictionary<AssetCategory, List<BaseAddressableData>>>  GetAllEntries()
        {
            return dataContainer?.GetAllEntries();
        }
    }
}

    """
    generate_file(os.path.join(ADDRESSABLE_LIB_DIR,"AddressableDataCore.cs"),code_str)

    code_str = """
    
using Cysharp.Threading.Tasks;
using System;
using UnityEngine;
using UnityEngine.AddressableAssets;
using UnityEngine.ResourceManagement.AsyncOperations;

namespace AddressableSystem
{
    [System.Serializable]
    public class AddressableObject<T> where T : UnityEngine.Object
    {
        [SerializeField] private bool isSetup;
        [SerializeField] private string addressablePath;
        [SerializeField] private T loadedObject;
        private bool isLoading;

        public bool IsSetup => isSetup;
        public T LoadedObject => loadedObject;
        public string AddressablePath
        {
            get => addressablePath;
            set => addressablePath = value;
        }

        public AddressableObject(string path)
        {
            addressablePath = path;
        }


        public async UniTask<T> LoadAsync(Action<T> action = null)
        {
            if (isLoading || isSetup || string.IsNullOrEmpty(addressablePath))
            {
                return loadedObject;
            }

            isLoading = true;
            try
            {
                var handle = Addressables.LoadAssetAsync<T>(addressablePath);
                loadedObject = await handle.ToUniTask();
                await UniTask.Yield(PlayerLoopTiming.Update);
                if (handle.Status == AsyncOperationStatus.Succeeded)
                {
                    isSetup = true;
                    action?.Invoke(loadedObject);
                    return loadedObject;
                }

                Debug.LogError($"Failed to load asset at {addressablePath}: {handle.OperationException}");
                return null;
            }
            catch (Exception ex)
            {
                Debug.LogError($"Exception loading asset at {addressablePath}: {ex.Message}");
                return null;
            }
            finally
            {
                isLoading = false;
            }
        }

        public GameObject Instantiate(string name = null)
        {
            if (!isSetup || loadedObject == null || loadedObject is not GameObject)
            {
                Debug.LogWarning("Cannot instantiate: Asset not loaded or not a GameObject.");
                return null;
            }

            var instantiated = GameObject.Instantiate(loadedObject as GameObject, Vector3.zero, Quaternion.identity);
            if (!string.IsNullOrEmpty(name))
            {
                instantiated.name = name;
            }
            return instantiated;
        }

        public void Release()
        {
            if (!isSetup || loadedObject == null) return;

            if (loadedObject is GameObject)
            {
                Addressables.ReleaseInstance(loadedObject as GameObject);
            }
            else
            {
                Addressables.Release(loadedObject);
            }
            loadedObject = null;
            isSetup = false;
        }
    }
}

    """
    generate_file(os.path.join(ADDRESSABLE_LIB_DIR,"AddressableObject.cs"),code_str)

    code_str = """
using UnityEngine;
using UnityEngine.SceneManagement;

namespace AddressableSystem
{
    /// <summary>
    /// 管理用の非ジェネリック基底。
    /// ロードメソッド自体は派生側に実装させる（T 型のラムダを受け取る）。
    /// </summary>
    
    public abstract class BaseAddressableData
    {
        protected bool isArray;
        public bool IsArray => isArray;
        protected bool isSetup;
        protected bool isLoaded;
        protected bool isAutoRelease;
        protected bool isUsed;
        public bool isCopy = false;

        protected UnityEngine.Object addressableObject;
        protected UnityEngine.Object[] addressableArray;

        public string path { get; protected set; }
        public GroupCategory groupCategory { get; protected set; }
        public AssetCategory assetCategory { get; protected set; }

        public Scene? SceneLink { get; set; }

        protected BaseAddressableData(GroupCategory group, AssetCategory category,string path,Scene? sceneLink = null)
        {
            SceneLink = sceneLink;
            groupCategory = group;
            assetCategory = category;
            this.path = path;
            AddressableDataCore.Instance.AddAddressableData(group, category, this, sceneLink);
        }

        public bool IsLoadedAndSetup => isSetup && isLoaded;
        public bool IsAutoRelease => isAutoRelease;
        public bool IsArray => isArray;
        public UnityEngine.Object GetAddressableObject() => addressableObject;
        public UnityEngine.Object[] GetAddressableArray() => addressableArray;
        public int GetArrayCount() => addressableArray?.Length ?? 0;

        public void EnableAutoRelease() => isAutoRelease = true;
        public void MarkAsUsed() => isUsed = true;

        /// <summary>
        /// 派生で実装する（型付きの Load/LoadArray を実装すること）。
        /// </summary>
        public abstract void Release();

        /// <summary>
        /// Single / SubGroup 単位の解放用。
        /// Release() に加えて AddressableDataCore の追跡リスト（AddressableDataContainer）からも
        /// 自分自身を除去する。これを呼ばないと、同じ path で再ロードした際に
        /// 「解放済みだが追跡リストに残ったままの古いエントリ」が Find() にヒットしてしまい、
        /// 新しいインスタンスが isCopy = true にされ、実体が二度とロードされない古いデータの
        /// 完了待ちで無限ループ（デッドロック）する不具合につながる。
        ///
        /// 注意: Group / Category 単位の一括解放（ReleaseGroup / ReleaseCategory 等）では
        /// 使用しないこと。呼び出し元がリストを foreach しながら Clear() する処理と衝突し、
        /// コレクション変更例外（InvalidOperationException）を誘発する。
        /// </summary>
        public void ReleaseAndUntrack()
        {
            Release();
            AddressableDataCore.Instance.RemoveData(this);
        }
    }
}




    """
    generate_file(os.path.join(ADDRESSABLE_LIB_DIR,"BaseAddressableData.cs"),code_str)

    code_str = """
#if UNITY_EDITOR
using System;
using System.Collections.Generic;
using System.Linq;
using UnityEditor;
using UnityEditor.AddressableAssets;
using UnityEditor.AddressableAssets.Settings;
using UnityEngine;

namespace AddressableSystem.EditorTools
{
    /// <summary>
    /// 現在ロード中のAddressable（Playモード時）と、プロジェクト内のAddressableグループ構成を
    /// 一覧できるエディタウィンドウ。
    /// Tools/Addressable/Addressable Manager から開く。
    /// </summary>
    public class AddressableManagerWindow : EditorWindow
    {
        private enum Tab { Runtime, Project }

        private Tab currentTab = Tab.Runtime;
        private Vector2 scrollPos;
        private string searchText = string.Empty;
        private bool autoRefresh = true;
        private double lastRefreshTime;

        private readonly Dictionary<GroupCategory, bool> groupFoldouts = new Dictionary<GroupCategory, bool>();
        private readonly Dictionary<string, bool> projectGroupFoldouts = new Dictionary<string, bool>();

        private static readonly Color HeaderColor = new Color(0.14f, 0.15f, 0.18f);
        private static readonly Color AccentColor = new Color(0.32f, 0.63f, 1.00f);
        private static readonly Color LoadedColor = new Color(0.35f, 0.80f, 0.45f);
        private static readonly Color PendingColor = new Color(0.95f, 0.65f, 0.25f);
        private static readonly Color MutedColor = new Color(0.62f, 0.62f, 0.66f);

        private GUIStyle _titleStyle;
        private GUIStyle _subtitleStyle;
        private GUIStyle _cardStyle;
        private GUIStyle _statValueStyle;
        private GUIStyle _pathStyle;
        private GUIStyle _tinyBoldStyle;
        private bool _stylesReady;

        [MenuItem("Tools/Addressable/Addressable Manager")]
        public static void Open()
        {
            var window = GetWindow<AddressableManagerWindow>();
            window.titleContent = new GUIContent("Addressable Manager");
            window.minSize = new Vector2(500, 420);
            window.Show();
        }

        private void OnEnable()
        {
            EditorApplication.update += OnEditorUpdate;
        }

        private void OnDisable()
        {
            EditorApplication.update -= OnEditorUpdate;
        }

        private void OnEditorUpdate()
        {
            if (!autoRefresh || !Application.isPlaying) return;
            if (EditorApplication.timeSinceStartup - lastRefreshTime < 0.5d) return;
            lastRefreshTime = EditorApplication.timeSinceStartup;
            Repaint();
        }

        private void EnsureStyles()
        {
            if (_stylesReady) return;
            _stylesReady = true;

            _titleStyle = new GUIStyle(EditorStyles.boldLabel) { fontSize = 15 };
            _titleStyle.normal.textColor = Color.white;

            _subtitleStyle = new GUIStyle(EditorStyles.miniLabel);
            _subtitleStyle.normal.textColor = MutedColor;

            _cardStyle = new GUIStyle(EditorStyles.helpBox);
            _cardStyle.padding = new RectOffset(10, 10, 8, 8);
            _cardStyle.margin = new RectOffset(2, 2, 4, 4);

            _statValueStyle = new GUIStyle(EditorStyles.boldLabel) { fontSize = 20 };

            _pathStyle = new GUIStyle(EditorStyles.label);
            _pathStyle.wordWrap = false;
            _pathStyle.fontSize = 11;

            _tinyBoldStyle = new GUIStyle(EditorStyles.miniBoldLabel);
        }

        private void OnGUI()
        {
            EnsureStyles();
            DrawHeader();
            DrawToolbar();

            scrollPos = EditorGUILayout.BeginScrollView(scrollPos);
            EditorGUILayout.Space(6);

            if (currentTab == Tab.Runtime)
            {
                DrawRuntimeTab();
            }
            else
            {
                DrawProjectTab();
            }

            EditorGUILayout.Space(12);
            EditorGUILayout.EndScrollView();
        }

        private void DrawHeader()
        {
            Rect rect = GUILayoutUtility.GetRect(position.width, 44);
            EditorGUI.DrawRect(rect, HeaderColor);

            var accentRect = new Rect(rect.x, rect.y + rect.height - 3, rect.width, 3);
            EditorGUI.DrawRect(accentRect, AccentColor);

            var titleRect = new Rect(rect.x + 12, rect.y + 4, rect.width - 24, 22);
            EditorGUI.LabelField(titleRect, "Addressable Manager", _titleStyle);

            string subtitle = Application.isPlaying
                ? "Play Mode - runtime load state"
                : "Edit Mode - project group configuration";
            var subRect = new Rect(rect.x + 12, rect.y + 24, rect.width - 24, 16);
            EditorGUI.LabelField(subRect, subtitle, _subtitleStyle);
        }

        private void DrawToolbar()
        {
            EditorGUILayout.Space(4);
            currentTab = (Tab)GUILayout.Toolbar((int)currentTab, new[] { "Runtime", "Project Groups" }, GUILayout.Height(22));

            EditorGUILayout.BeginHorizontal();
            GUILayout.Label("Search", GUILayout.Width(46));
            searchText = EditorGUILayout.TextField(searchText);
            if (GUILayout.Button("Refresh", GUILayout.Width(64)))
            {
                Repaint();
            }
            autoRefresh = GUILayout.Toggle(autoRefresh, "Auto", "Button", GUILayout.Width(50));
            EditorGUILayout.EndHorizontal();
        }

        // ------------------------------------------------------------
        // Runtime tab
        // ------------------------------------------------------------
        private void DrawRuntimeTab()
        {
            if (!Application.isPlaying)
            {
                EditorGUILayout.Space(20);
                EditorGUILayout.HelpBox(
                    "Playモード中に AddressableDataCore が管理しているロード状況をここに表示します。\n" +
                    "Playを開始すると自動的に更新されます。",
                    MessageType.Info);
                return;
            }

            AddressableDataCore core = AddressableDataCore.Instance;
            Dictionary<GroupCategory, Dictionary<AssetCategory, List<BaseAddressableData>>> entries = core.GetAllEntries();

            if (!string.IsNullOrEmpty(searchText))
            {
                entries = entries.ToDictionary(
                    g => g.Key,
                    g => g.Value.ToDictionary(
                        c => c.Key,
                        c => c.Value.Where(e => e.path != null && e.path.IndexOf(searchText, StringComparison.OrdinalIgnoreCase) >= 0).ToList()
                    )
                );
            }

            int total = entries.Count;
            int loaded = entries.Sum(g => g.Value.Sum(c => c.Value.Count(e => e.IsLoadedAndSetup)));
            DrawSummaryCard(total, loaded);

            EditorGUILayout.Space(6);

            List<GroupCategory> groups = entries.Keys.OrderBy(g => g.ToString()).ToList();

            if (groups.Count == 0)
            {
                EditorGUILayout.HelpBox("現在ロード中のAddressableはありません。", MessageType.Info);
                return;
            }

            foreach (GroupCategory group in groups)
            {
                List<BaseAddressableData> groupEntries = entries[group].SelectMany(c => c.Value).ToList();
                DrawGroupCard(group, groupEntries, core);
            }
        }

        private void DrawSummaryCard(int total, int loaded)
        {
            EditorGUILayout.BeginVertical(_cardStyle);
            EditorGUILayout.BeginHorizontal();
            DrawStat("Total", total.ToString(), AccentColor);
            DrawStat("Loaded", loaded.ToString(), LoadedColor);
            DrawStat("Pending", (total - loaded).ToString(), PendingColor);
            EditorGUILayout.EndHorizontal();
            EditorGUILayout.EndVertical();
        }

        private void DrawStat(string label, string value, Color color)
        {
            EditorGUILayout.BeginVertical(GUILayout.Width(100));
            GUIStyle style = new GUIStyle(_statValueStyle);
            style.normal.textColor = color;
            GUILayout.Label(value, style);
            GUILayout.Label(label, _subtitleStyle);
            EditorGUILayout.EndVertical();
        }

        private void DrawGroupCard(GroupCategory group, List<BaseAddressableData> entries, AddressableDataCore core)
        {
            if (!groupFoldouts.ContainsKey(group))
            {
                groupFoldouts[group] = true;
            }

            EditorGUILayout.BeginVertical(_cardStyle);

            EditorGUILayout.BeginHorizontal();
            groupFoldouts[group] = EditorGUILayout.Foldout(groupFoldouts[group], group + "  (" + entries.Count + ")", true);
            GUILayout.FlexibleSpace();
            if (GUILayout.Button("Release", GUILayout.Width(70)))
            {
                if (EditorUtility.DisplayDialog("Release Group", group + " グループを全て解放しますか？", "Release", "Cancel"))
                {
                    core.ReleaseGroup(group);
                }
            }
            EditorGUILayout.EndHorizontal();

            if (groupFoldouts[group])
            {
                IEnumerable<AssetCategory> categories = entries.Select(e => e.assetCategory).Distinct().OrderBy(c => c.ToString());
                foreach (AssetCategory category in categories)
                {
                    List<BaseAddressableData> categoryEntries = entries.Where(e => e.assetCategory == category).ToList();
                    DrawCategorySection(group, category, categoryEntries, core);
                }
            }

            EditorGUILayout.EndVertical();
        }

        private void DrawCategorySection(GroupCategory group, AssetCategory category, List<BaseAddressableData> entries, AddressableDataCore core)
        {
            EditorGUI.indentLevel++;
            EditorGUILayout.BeginHorizontal();
            GUILayout.Label("- " + category, _tinyBoldStyle, GUILayout.Width(140));
            int loadedCount = entries.Count(e => e.IsLoadedAndSetup);
            GUILayout.Label(loadedCount + "/" + entries.Count + " loaded", _subtitleStyle);
            GUILayout.FlexibleSpace();
            if (GUILayout.Button("Release", GUILayout.Width(70)))
            {
                if (EditorUtility.DisplayDialog("Release Category", group + " / " + category + " を解放しますか？", "Release", "Cancel"))
                {
                    core.ReleaseCategory(group, category);
                }
            }
            EditorGUILayout.EndHorizontal();

            foreach (BaseAddressableData entry in entries)
            {
                DrawEntryRow(entry);
            }

            EditorGUI.indentLevel--;
            EditorGUILayout.Space(2);
        }

        private void DrawEntryRow(BaseAddressableData entry)
        {
            EditorGUILayout.BeginHorizontal();

            Color statusColor = entry.IsLoadedAndSetup ? LoadedColor : PendingColor;
            Color prevColor = GUI.color;
            GUI.color = statusColor;
            GUILayout.Label("*", GUILayout.Width(14));
            GUI.color = prevColor;

            string label = string.IsNullOrEmpty(entry.path) ? "(no path)" : entry.path;
            GUILayout.Label(label, _pathStyle);

            GUILayout.FlexibleSpace();

            if (entry.IsArray)
            {
                GUILayout.Label("x" + entry.GetArrayCount(), _subtitleStyle, GUILayout.Width(36));
            }
            if (entry.IsAutoRelease)
            {
                GUILayout.Label("auto", _subtitleStyle, GUILayout.Width(34));
            }

            EditorGUILayout.EndHorizontal();
        }

        // ------------------------------------------------------------
        // Project tab（Editモードでも見られる、プロジェクト内のAddressableグループ構成）
        // ------------------------------------------------------------
        private void DrawProjectTab()
        {
            AddressableAssetSettings settings = AddressableAssetSettingsDefaultObject.Settings;
            if (settings == null)
            {
                EditorGUILayout.HelpBox(
                    "Addressable Asset Settings が見つかりません。\n" +
                    "Window > Asset Management > Addressables > Groups からセットアップしてください。",
                    MessageType.Warning);
                return;
            }

            List<AddressableAssetGroup> groups = settings.groups.Where(g => g != null).ToList();

            EditorGUILayout.BeginVertical(_cardStyle);
            EditorGUILayout.BeginHorizontal();
            DrawStat("Groups", groups.Count.ToString(), AccentColor);
            DrawStat("Entries", groups.Sum(g => g.entries.Count).ToString(), LoadedColor);
            EditorGUILayout.EndHorizontal();
            EditorGUILayout.EndVertical();

            EditorGUILayout.Space(6);

            foreach (AddressableAssetGroup group in groups)
            {
                DrawProjectGroupCard(group, group == settings.DefaultGroup);
            }
        }

        private void DrawProjectGroupCard(AddressableAssetGroup group, bool isDefault)
        {
            if (!projectGroupFoldouts.ContainsKey(group.Name))
            {
                projectGroupFoldouts[group.Name] = false;
            }

            List<AddressableAssetEntry> entries = group.entries.ToList();
            if (!string.IsNullOrEmpty(searchText))
            {
                entries = entries
                    .Where(e => e.address != null && e.address.IndexOf(searchText, StringComparison.OrdinalIgnoreCase) >= 0)
                    .ToList();
                if (entries.Count == 0) return;
            }

            EditorGUILayout.BeginVertical(_cardStyle);
            EditorGUILayout.BeginHorizontal();
            projectGroupFoldouts[group.Name] = EditorGUILayout.Foldout(
                projectGroupFoldouts[group.Name], group.Name + "  (" + entries.Count + ")", true);
            GUILayout.FlexibleSpace();
            if (isDefault)
            {
                GUILayout.Label("Default", _subtitleStyle, GUILayout.Width(50));
            }
            if (GUILayout.Button("Select", GUILayout.Width(60)))
            {
                Selection.activeObject = group;
                EditorGUIUtility.PingObject(group);
            }
            EditorGUILayout.EndHorizontal();

            if (projectGroupFoldouts[group.Name])
            {
                EditorGUI.indentLevel++;
                foreach (AddressableAssetEntry entry in entries)
                {
                    EditorGUILayout.BeginHorizontal();
                    GUILayout.Label(entry.address, _pathStyle);
                    GUILayout.FlexibleSpace();
                    string typeName = entry.MainAssetType != null ? entry.MainAssetType.Name : "?";
                    GUILayout.Label(typeName, _subtitleStyle, GUILayout.Width(90));
                    if (GUILayout.Button("Ping", GUILayout.Width(44)))
                    {
                        UnityEngine.Object asset = AssetDatabase.LoadMainAssetAtPath(entry.AssetPath);
                        if (asset != null)
                        {
                            Selection.activeObject = asset;
                            EditorGUIUtility.PingObject(asset);
                        }
                    }
                    EditorGUILayout.EndHorizontal();
                }
                EditorGUI.indentLevel--;
            }

            EditorGUILayout.EndVertical();
        }
    }
}
#endif"""
    generate_file(os.path.join(ADDRESSABLE_EDITOR_DIR,"AddressableManagerWindow.cs"),code_str.strip() + "\\n")

    code_str = """
    # AddressableSupportLib

    Unity Addressablesを効率的・柔軟に管理/活用するためのC#ライブラリです。  
    アドレッサブルアセットのロード・管理・解放を抽象化し、プロジェクトの規模や用途に応じた柔軟なリソース管理をサポートします。

    ---

    ## 特長

    - **アドレッサブルアセットの型安全なロード/管理**
    - **グループ・カテゴリ単位での整理・検索・一括解放**
    - **シーンリンクや自動解放(AutoRelease)の仕組み**
    - **シンプルなAPIとシングルトンによる統合管理**

    ---

    ## 主な構成

    - `BaseAddressableData.cs`  
      アドレッサブルデータの抽象基底クラス。ロード状態や自動解放フラグなど共通管理を提供。

    - `AddressableData.cs`  
      型付き(T)アドレッサブルデータの実装。  
      単体/配列ロード、インスタンス生成、解放(Release)処理を提供。

    - `AddressableObject.cs`  
      アドレッサブルアセットの汎用ラッパー。  
      非同期ロード、インスタンス化、リリースを簡潔に呼び出し可能。

    - `AddressableDataContainer.cs`  
      グループ・カテゴリでデータを管理するコンテナ。  
      検索・追加・一括解放・統計情報などを提供。

    - `AddressableDataCore.cs`  
      ライブラリの中核となるシングルトンクラス。  
      AddressableDataContainerによる一元管理、シーンごとの管理、  
      自動解放ルーチン、各種ファクトリメソッドなどを実装。

    ---

    ## 使い方

    ### 1. AddressableObjectで単体ロード

    ```csharp
    var addressable = AddressableDataCore.CreateAddressable<GameObject>("Assets/Prefabs/MyPrefab.prefab");
    await addressable.LoadAsync(obj => {
        // obj: ロードされたGameObject
    });
    ```

    ### 2. AddressableDataを使った拡張管理

    ```csharp
    var data = new AddressableData<GameObject>(
        GroupCategory.Game,
        AssetCategory.Prefab
    );
    await data.LoadAsync("Assets/Prefabs/MyPrefab.prefab", obj => {
        // obj 利用
    });

    // インスタンス化
    var instance = data.Instantiate("MyInstance");
    ```

    ### 3. グループ/カテゴリ単位で一括解放

    ```csharp
    AddressableDataCore.Instance.ReleaseGroup(GroupCategory.Game);
    AddressableDataCore.Instance.ReleaseCategory(GroupCategory.Game, AssetCategory.Prefab);
    ```

    ### 4. 自動解放(AutoRelease)の利用

    ```csharp
    data.EnableAutoRelease();
    // 未使用になったら自動解放ルーチンでメモリ開放
    ```

    ---

    ## 列挙体(Enums)

    - **AssetCategory**  
      - Prefab / Texture / Audio / UI / Other
    - **GroupCategory**  
      - Title / Game / Exit / Menu / Other

    ---

    ## 依存

    - Unity (Addressables, ResourceManagement)
    - Cysharp UniTask

    ---

    ## 注意事項

    - Addressablesシステムのセットアップは別途必要です  
    - 各APIの詳細挙動はコードコメントを参照してください

    ---

    ## ライセンス

    MIT License

    ---

    ## 作者

    [ChigaDio](https://github.com/ChigaDio)
    """
    generate_file(os.path.join(ADDRESSABLE_LIB_DIR,"README.md"),code_str)