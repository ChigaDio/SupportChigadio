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
SAVE_DATA_DIR = os.path.join(DATA_DIR, "save_data")
SAVE_DATA_CUSTOM_DIR = os.path.join(SAVE_DATA_DIR, "custom_data")

def init(data_dir):
    """app.py から呼び出す初期化関数。"""
    global DATA_DIR, SAVE_DATA_DIR, SAVE_DATA_CUSTOM_DIR
    DATA_DIR = os.path.abspath(data_dir)
    SAVE_DATA_DIR = os.path.join(DATA_DIR, "save_data")
    SAVE_DATA_CUSTOM_DIR = os.path.join(SAVE_DATA_DIR, "custom_data")

def generate_base():
    if not os.path.exists(SAVE_DATA_DIR):
        os.makedirs(SAVE_DATA_DIR)

    # ── SaveDataVersion.cs ──
    # Main.Sub.Details(int×3)のバージョン比較・ダウングレード検知ユーティリティ。
    # Base{SystemData,PlayerData}.cs 側で生成される VersionMain/Sub/Details(const)と
    # SavedVersionMain/Sub/Details(実際にセーブされる側)の比較にSaveManager.csから使う。
    if not os.path.exists(os.path.join(SAVE_DATA_DIR, "SaveDataVersion.cs")):
        code_str = """
using System;

namespace GameCore.SaveSystem
{
    /// <summary>
    /// Main.Sub.Details の3つのintで構成されるSaveDataバージョン。
    /// </summary>
    public readonly struct SaveDataVersion : IEquatable<SaveDataVersion>
    {
        public readonly int Main;
        public readonly int Sub;
        public readonly int Details;

        public SaveDataVersion(int main, int sub, int details)
        {
            Main = main;
            Sub = sub;
            Details = details;
        }

        /// <summary>
        /// このバージョンが other より新しければ1、同じなら0、古ければ-1。
        /// </summary>
        public int CompareTo(SaveDataVersion other)
        {
            if (Main != other.Main) return Main > other.Main ? 1 : -1;
            if (Sub != other.Sub) return Sub > other.Sub ? 1 : -1;
            if (Details != other.Details) return Details > other.Details ? 1 : -1;
            return 0;
        }

        public bool Equals(SaveDataVersion other) => Main == other.Main && Sub == other.Sub && Details == other.Details;
        public override bool Equals(object obj) => obj is SaveDataVersion v && Equals(v);
        public override int GetHashCode() => (Main * 397 ^ Sub) * 397 ^ Details;
        public override string ToString() => Main + "." + Sub + "." + Details;

        public static bool operator >(SaveDataVersion a, SaveDataVersion b) => a.CompareTo(b) > 0;
        public static bool operator <(SaveDataVersion a, SaveDataVersion b) => a.CompareTo(b) < 0;
        public static bool operator >=(SaveDataVersion a, SaveDataVersion b) => a.CompareTo(b) >= 0;
        public static bool operator <=(SaveDataVersion a, SaveDataVersion b) => a.CompareTo(b) <= 0;
        public static bool operator ==(SaveDataVersion a, SaveDataVersion b) => a.Equals(b);
        public static bool operator !=(SaveDataVersion a, SaveDataVersion b) => !a.Equals(b);
    }

    /// <summary>
    /// プログラム側のバージョンより新しい(=ダウングレード)SaveDataを読み込もうとした場合の例外。
    /// Debug.Errorでのログのみで済ませず、呼び出し側で確実にハンドリングできるよう例外として投げる。
    /// </summary>
    public sealed class SaveDataDowngradeException : Exception
    {
        public readonly SaveDataVersion ProgramVersion;
        public readonly SaveDataVersion SaveVersion;

        public SaveDataDowngradeException(string dataName, SaveDataVersion programVersion, SaveDataVersion saveVersion)
            : base(dataName + " のSaveDataバージョン(" + saveVersion + ")が実行中プログラムのバージョン(" + programVersion + ")より新しいため読み込めません(ダウングレード不可)。")
        {
            ProgramVersion = programVersion;
            SaveVersion = saveVersion;
        }
    }

    public static class SaveDataVersionValidator
    {
        /// <summary>
        /// programVersion: 実行中プログラム側の定数バージョン。
        /// saveVersion: ロードしたSaveDataに記録されていたバージョン(ref)。
        /// プログラムの方が新しい場合、この場でprogramVersionへ上書きする
        /// (＝以後の保存時に新しいバージョンとして書き戻される)。
        /// 戻り値: true = 読み込み続行可。false = ダウングレード検知(エラー)。
        /// </summary>
        public static bool TryValidateAndUpgrade(SaveDataVersion programVersion, ref SaveDataVersion saveVersion)
        {
            int cmp = saveVersion.CompareTo(programVersion);
            if (cmp > 0)
            {
                // SaveData側の方が新しい = ダウングレードして読み込もうとしている
                return false;
            }
            if (cmp < 0)
            {
                // プログラム側の方が新しい: SaveData側のバージョンをプログラムのバージョンで上書き
                saveVersion = programVersion;
            }
            return true;
        }

        /// <summary>
        /// TryValidateAndUpgradeのラッパー。失敗時はDebug.Errorではなく例外を投げる。
        /// </summary>
        public static void ValidateAndUpgradeOrThrow(string dataName, SaveDataVersion programVersion, ref SaveDataVersion saveVersion)
        {
            if (!TryValidateAndUpgrade(programVersion, ref saveVersion))
            {
                throw new SaveDataDowngradeException(dataName, programVersion, saveVersion);
            }
        }
    }
}
        """
        with open(os.path.join(SAVE_DATA_DIR, "SaveDataVersion.cs"), 'w', encoding='utf-8') as f:
            f.write(code_str)

    if not os.path.exists(os.path.join(SAVE_DATA_DIR, "SaveManagerCore .cs")):
        code_str = """
        using Cysharp.Threading.Tasks;
using System;
using UnityEngine;

namespace GameCore.SaveSystem
{
    [AddComponentMenu("GameCore/Save Manager Core")]
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

            systemDataPath = Path.Combine(saveDir, "systemData.bytes");
            playerDataPath = Path.Combine(saveDir, "playerData.bytes");

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
            string json = JsonUtility.ToJson(data);
            return System.Text.Encoding.UTF8.GetBytes(json);
        }

        private T DeserializeFromBinary<T>(byte[] data)
        {
            string json = System.Text.Encoding.UTF8.GetString(data);
            return JsonUtility.FromJson<T>(json);
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
                        ValidateAndUpgradeSystemDataVersion();
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
            catch (SaveDataDowngradeException)
            {
                // ダウングレード(セーブデータの方がプログラムより新しい)はDebug.Errorで
                // 揉み消さず、呼び出し元がcatchして対処(エラー画面表示等)できるよう再送出する。
                IsLoading = false;
                throw;
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

        /// <summary>
        /// ロードしたSystemSettings.SavedVersion*と、現在のプログラムが持つ
        /// SystemData.VersionMain/Sub/Details(const)を比較する。
        /// セーブデータの方が新しければ SaveDataDowngradeException を投げる(ダウングレード禁止)。
        /// プログラムの方が新しければ、SystemSettings側のSavedVersion*をプログラムの
        /// バージョンで上書きする(次回保存時にアップグレードされたバージョンが書き戻る)。
        /// </summary>
        private void ValidateAndUpgradeSystemDataVersion()
        {
            var programVersion = new SaveDataVersion(SystemData.VersionMain, SystemData.VersionSub, SystemData.VersionDetails);
            var saveVersion = new SaveDataVersion(SystemSettings.SavedVersionMain, SystemSettings.SavedVersionSub, SystemSettings.SavedVersionDetails);
            SaveDataVersionValidator.ValidateAndUpgradeOrThrow("SystemData", programVersion, ref saveVersion);
            SystemSettings.SavedVersionMain = saveVersion.Main;
            SystemSettings.SavedVersionSub = saveVersion.Sub;
            SystemSettings.SavedVersionDetails = saveVersion.Details;
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
                        ValidateAndUpgradePlayerDataVersion();
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
            catch (SaveDataDowngradeException)
            {
                // ダウングレード(セーブデータの方がプログラムより新しい)はDebug.Errorで
                // 揉み消さず、呼び出し元がcatchして対処(エラー画面表示等)できるよう再送出する。
                IsLoading = false;
                throw;
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

        /// <summary>
        /// ロードしたPlayerProgress.SavedVersion*と、現在のプログラムが持つ
        /// PlayerData.VersionMain/Sub/Details(const)を比較する。
        /// セーブデータの方が新しければ SaveDataDowngradeException を投げる(ダウングレード禁止)。
        /// プログラムの方が新しければ、PlayerProgress側のSavedVersion*をプログラムの
        /// バージョンで上書きする(次回保存時にアップグレードされたバージョンが書き戻る)。
        /// </summary>
        private void ValidateAndUpgradePlayerDataVersion()
        {
            var programVersion = new SaveDataVersion(PlayerData.VersionMain, PlayerData.VersionSub, PlayerData.VersionDetails);
            var saveVersion = new SaveDataVersion(PlayerProgress.SavedVersionMain, PlayerProgress.SavedVersionSub, PlayerProgress.SavedVersionDetails);
            SaveDataVersionValidator.ValidateAndUpgradeOrThrow("PlayerData", programVersion, ref saveVersion);
            PlayerProgress.SavedVersionMain = saveVersion.Main;
            PlayerProgress.SavedVersionSub = saveVersion.Sub;
            PlayerProgress.SavedVersionDetails = saveVersion.Details;
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
        public float seVolume = 1.0f;
        public float bgmVolume = 1.0f;
        public float voiceVolume = 1.0f;
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

        



