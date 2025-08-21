export const fetchEnumIdData = async () => {
  const response = await fetch('/api/enum-id');
  const data = await response.json();
  return data;
};