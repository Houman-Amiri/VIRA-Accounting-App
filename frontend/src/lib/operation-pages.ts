/** Production order picker must not silently hide orders beyond the first page. */
export async function collectOperationPages<T>(
  load: (offset: number, limit: number) => Promise<T[]>,
): Promise<T[]> {
  const rows: T[] = [];
  const size = 500;
  for (let offset = 0; ; offset += size) {
    const page = await load(offset, size);
    rows.push(...page);
    if (page.length < size) return rows;
  }
}
