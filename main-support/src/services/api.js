export const fetchEnumIdData = async () => {
  const response = await fetch('/api/enum-id');
  const data = await response.json();
  return data;
};

// 削除前の横断参照チェック。
// Enum/ClassData/ClassDataID/CustomClassData/CustomClassDataID/State/Behavior/
// ScenarioRole 等の「型」を削除する前に、他のデータがその型を参照していないかを
// バックエンド(/api/reference-check)に問い合わせ、参照がある場合は内容を含めた
// 確認ダイアログを出す。参照が無ければ通常の確認ダイアログのみ。
// チェック自体がエラーになった場合（ネットワーク不調等）は、削除操作自体を
// ブロックしないよう通常の確認ダイアログにフォールバックする。
export const confirmDeleteWithReferenceCheck = async (category, name, itemLabel) => {
  const label = itemLabel || name;
  try {
    const res = await fetch(`/api/reference-check/${category}/${encodeURIComponent(name)}`);
    if (res.ok) {
      const data = await res.json();
      const refs = data.references || [];
      if (refs.length > 0) {
        const lines = refs
          .map((r) => `・${r.category}/${r.name}（フィールド: ${r.fields.join(', ')}）`)
          .join('\n');
        return window.confirm(
          `「${label}」は以下の${refs.length}件から参照されています。\n` +
          '削除すると、それらのC#生成時にコンパイルエラーになる可能性があります。\n\n' +
          `${lines}\n\n本当に削除しますか？`
        );
      }
    }
  } catch (e) {
    console.warn('参照チェックに失敗しました（削除確認は続行します）:', e);
  }
  return window.confirm(`「${label}」を削除しますか？`);
};