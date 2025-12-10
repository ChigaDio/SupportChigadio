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
SAVE_DATA_DIR = os.path.join(DATA_DIR, "save-data")
SAVE_DATA_CUSTOM_DIR = os.path.join(SAVE_DATA_DIR, "custom-data")

def generate_base():
    if not os.path.exists(SAVE_DATA_DIR):
        os.makedirs(SAVE_DATA_DIR)

    if not os.path.exists(os.path.join(SAVE_DATA_DIR, "SaveManagerCore .cs")):
        code_str = """
        using Cysharp.Threading.Tasks;
using System;
using UnityEngine;

namespace GameCore.SaveSystem
{
    public class SaveManagerCore : BaseSingleton<SaveManagerCore>
    {
        private SaveManager saveManager;

        public SystemData SystemSettings => saveManager.SystemSettings;
        public PlayerData PlayerProgress => saveManager.PlayerProgress;
        public bool IsSaving => saveManager.IsSaving;
        public bool IsLoading => saveManager.IsLoading;

        public bool IsSaveLoadActionNow()
        {
            return (IsSaving | IsLoading);
        }

        public override void AwakeSingleton()
        {
            base.AwakeSingleton();
            DontDestroyOnLoad(gameObject);
            saveManager = new SaveManager(gameObject);
            LoadAllDataAsync().Forget();
        }

        public async UniTask LoadAllDataAsync(Action onComplete = null)
        {
            await saveManager.LoadAllDataAsync(onComplete);
        }

        public async UniTask SaveAllDataAsync(Action onComplete = null)
        {
            await saveManager.SaveAllDataAsync(onComplete);
        }

        public async UniTask LoadSystemDataAsync(Action onComplete = null)
        {
            await saveManager.LoadSystemDataAsync(onComplete);
        }

        public async UniTask SaveSystemDataAsync(Action onComplete = null)
        {
            await saveManager.SaveSystemDataAsync(onComplete);
        }

        public async UniTask LoadPlayerDataAsync(Action onComplete = null)
        {
            await saveManager.LoadPlayerDataAsync(onComplete);
        }

        public async UniTask SavePlayerDataAsync(Action onComplete = null)
        {
            await saveManager.SavePlayerDataAsync(onComplete);
        }

        private void OnDestroy()
        {
            saveManager?.Dispose();
        }
    }
}
        """
        with open(os.path.join(SAVE_DATA_DIR, "SaveManagerCore .cs"), 'w', encoding='utf-8') as f:
            f.write(code_str)

    if not os.path.exists(os.path.join(SAVE_DATA_DIR, "SaveManager.cs")):
        code_str = """
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.Serialization.Formatters.Binary;
using System.Threading;
using Cysharp.Threading.Tasks;
using UnityEngine;

namespace GameCore.SaveSystem
{


    public class SaveManager
    {
        private readonly string systemDataPath;
        private readonly string playerDataPath;
        private readonly CancellationTokenSource cts;
        private readonly byte[] encryptionKey = { 0xA1, 0xB2, 0xC3, 0xD4, 0xE5, 0xF6, 0x07, 0x18 };
        public SystemData SystemSettings { get; private set; } = new SystemData();
        public PlayerData PlayerProgress { get; private set; } = new PlayerData();
        public bool IsSaving { get; private set; }
        public bool IsLoading { get; private set; }

        public SaveManager(GameObject linkedGameObject)
        {
            string saveDir;
#if UNITY_EDITOR
            saveDir = Path.Combine(Application.dataPath, "SaveData");
#else
            saveDir = Path.Combine(Application.dataPath, "SaveData");
#endif
            Directory.CreateDirectory(saveDir);

            systemDataPath = Path.Combine(saveDir, "systemData.bin");
            playerDataPath = Path.Combine(saveDir, "playerData.bin");

            cts = new CancellationTokenSource();
            if (linkedGameObject != null)
            {
                CancellationTokenSource linkedCts = CancellationTokenSource.CreateLinkedTokenSource(cts.Token);
                linkedGameObject.GetCancellationTokenOnDestroy().Register(() => linkedCts.Cancel());
            }
        }

        private byte[] EncryptDecrypt(byte[] data)
        {
            byte[] result = new byte[data.Length];
            for (int i = 0; i < data.Length; i++)
            {
                result[i] = (byte)(data[i] ^ encryptionKey[i % encryptionKey.Length]);
            }
            return result;
        }

        private byte[] SerializeToBinary<T>(T data)
        {
            using (MemoryStream ms = new MemoryStream())
            {
                BinaryFormatter formatter = new BinaryFormatter();
                formatter.Serialize(ms, data);
                return ms.ToArray();
            }
        }

        private T DeserializeFromBinary<T>(byte[] data)
        {
            using (MemoryStream ms = new MemoryStream(data))
            {
                BinaryFormatter formatter = new BinaryFormatter();
                return (T)formatter.Deserialize(ms);
            }
        }

        public async UniTask LoadAllDataAsync(Action onComplete = null)
        {
            try
            {
                IsLoading = true;
                await UniTask.WhenAll(
                    LoadSystemDataAsync(),
                    LoadPlayerDataAsync()
                );
                onComplete?.Invoke();
            }
            catch (OperationCanceledException)
            {
                Debug.Log("LoadAllDataAsyncがキャンセルされました。");
            }
            catch (Exception ex)
            {
                Debug.LogError($"LoadAllDataAsyncでエラー: {ex.Message}");
            }
            finally
            {
                IsLoading = false;
                onComplete?.Invoke();
            }
        }

        public async UniTask SaveAllDataAsync(Action onComplete = null)
        {
            try
            {
                IsSaving = true;
                await UniTask.WhenAll(
                    SaveSystemDataAsync(),
                    SavePlayerDataAsync()
                );
                onComplete?.Invoke();
            }
            catch (OperationCanceledException)
            {
                Debug.Log("SaveAllDataAsyncがキャンセルされました。");
            }
            catch (Exception ex)
            {
                Debug.LogError($"SaveAllDataAsyncでエラー: {ex.Message}");
            }
            finally
            {
                IsSaving = false;
                onComplete?.Invoke();
            }
        }

        public async UniTask LoadSystemDataAsync(Action onComplete = null)
        {
            try
            {
                IsLoading = true;
                await UniTask.RunOnThreadPool(() =>
                {
                    if (File.Exists(systemDataPath))
                    {
                        byte[] encryptedData = File.ReadAllBytes(systemDataPath);
                        byte[] decryptedData = EncryptDecrypt(encryptedData);
                        SystemSettings = DeserializeFromBinary<SystemData>(decryptedData) ?? new SystemData();
                        Debug.Log($"システムデータを読み込みました: {systemDataPath}");
                    }
                    else
                    {
                        SystemSettings = new SystemData();
                        SaveSystemDataAsync().Forget();
                        Debug.Log($"システムデータファイルが見つかりませんでした。デフォルトを使用: {systemDataPath}");
                    }
                }, cancellationToken: cts.Token);
                onComplete?.Invoke();
            }
            catch (OperationCanceledException)
            {
                Debug.Log("LoadSystemDataAsyncがキャンセルされました。");
            }
            catch (Exception ex)
            {
                Debug.LogError($"LoadSystemDataAsyncでエラー: {ex.Message}");
            }
            finally
            {
                IsLoading = false;
                onComplete?.Invoke();
            }
        }

        public async UniTask SaveSystemDataAsync(Action onComplete = null)
        {
            try
            {
                IsSaving = true;
                await UniTask.RunOnThreadPool(() =>
                {
                    byte[] data = SerializeToBinary(SystemSettings);
                    byte[] encryptedData = EncryptDecrypt(data);
                    File.WriteAllBytes(systemDataPath, encryptedData);
                    Debug.Log($"システムデータを保存しました: {systemDataPath}");
                }, cancellationToken: cts.Token);
                onComplete?.Invoke();
            }
            catch (OperationCanceledException)
            {
                Debug.Log("SaveSystemDataAsyncがキャンセルされました。");
            }
            catch (Exception ex)
            {
                Debug.LogError($"SaveSystemDataAsyncでエラー: {ex.Message}");
            }
            finally
            {
                IsSaving = false;
                onComplete?.Invoke();
            }
        }

        public async UniTask LoadPlayerDataAsync(Action onComplete = null)
        {
            try
            {
                IsLoading = true;
                await UniTask.RunOnThreadPool(() =>
                {
                    if (File.Exists(playerDataPath))
                    {
                        byte[] encryptedData = File.ReadAllBytes(playerDataPath);
                        byte[] decryptedData = EncryptDecrypt(encryptedData);
                        PlayerProgress = DeserializeFromBinary<PlayerData>(decryptedData) ?? new PlayerData();
                        Debug.Log($"プレイヤーデータを読み込みました: {playerDataPath}");
                    }
                    else
                    {
                        PlayerProgress = new PlayerData();
                        SavePlayerDataAsync().Forget();
                        Debug.Log($"プレイヤーデータファイルが見つかりませんでした。新規作成: {playerDataPath}");
                    }
                }, cancellationToken: cts.Token);
                onComplete?.Invoke();
            }
            catch (OperationCanceledException)
            {
                Debug.Log("LoadPlayerDataAsyncがキャンセルされました。");
            }
            catch (Exception ex)
            {
                Debug.LogError($"LoadPlayerDataAsyncでエラー: {ex.Message}");
            }
            finally
            {
                IsLoading = false;
                onComplete?.Invoke();
            }
        }

        public async UniTask SavePlayerDataAsync(Action onComplete = null)
        {
            try
            {
                IsSaving = true;
                await UniTask.RunOnThreadPool(() =>
                {
                    byte[] data = SerializeToBinary(PlayerProgress);
                    byte[] encryptedData = EncryptDecrypt(data);
                    File.WriteAllBytes(playerDataPath, encryptedData);
                    Debug.Log($"プレイヤーデータを保存しました: {playerDataPath}");
                }, cancellationToken: cts.Token);
                onComplete?.Invoke();
            }
            catch (OperationCanceledException)
            {
                Debug.Log("SavePlayerDataAsyncがキャンセルされました。");
            }
            catch (Exception ex)
            {
                Debug.LogError($"SavePlayerDataAsyncでエラー: {ex.Message}");
            }
            finally
            {
                IsSaving = false;
                onComplete?.Invoke();
            }
        }

        public void Dispose()
        {
            cts?.Cancel();
            cts?.Dispose();
        }
    }
}
        """

        with open(os.path.join(SAVE_DATA_DIR, "SaveManager.cs"), "w") as f:
            f.write(code_str)


    if not os.path.exists(SAVE_DATA_CUSTOM_DIR):
        os.makedirs(SAVE_DATA_CUSTOM_DIR)
        
    if not os.path.exists(os.path.join(SAVE_DATA_CUSTOM_DIR, "BaseSystemData.cs")):
        code_str = """
using System;
using UnityEngine;
namespace GameCore.SaveSystem
{
    [Serializable]
    public class BaseSystemData
    {
    }
}
        """
        with open(os.path.join(SAVE_DATA_CUSTOM_DIR, "BaseSystemData.cs"), "w") as f:
            f.write(code_str)
    
    if not os.path.exists(os.path.join(SAVE_DATA_CUSTOM_DIR, "BasePlayerData.cs")):
        code_str = """
using System;
using UnityEngine;
namespace GameCore.SaveSystem
{
    [Serializable]
    public class BasePlayerData
    {
    }
}
        """
        with open(os.path.join(SAVE_DATA_CUSTOM_DIR, "BasePlayerData.cs"), "w") as f:
            f.write(code_str)

    if not os.path.exists(os.path.join(SAVE_DATA_CUSTOM_DIR, "SystemData.cs")):
        code_str = """
using System;
using UnityEngine;
namespace GameCore.SaveSystem
{
    [Serializable]
    public class SystemData : BaseSystemData
    {
    }
}
        """
        with open(os.path.join(SAVE_DATA_CUSTOM_DIR, "SystemData.cs"), "w") as f:
            f.write(code_str)
    
    if not os.path.exists(os.path.join(SAVE_DATA_CUSTOM_DIR, "PlayerData.cs")):
        code_str = """
using System;
using UnityEngine;
namespace GameCore.SaveSystem
{
    [Serializable]
    public class PlayerData : BasePlayerData
    {
    }
}
        """
        with open(os.path.join(SAVE_DATA_CUSTOM_DIR, "PlayerData.cs"), "w") as f:
            f.write(code_str)

        



