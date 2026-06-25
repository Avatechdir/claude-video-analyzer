# plan_frames.awk — строит план таймкодов кадров из карты сцен и интервалов тишины.
# Идея: кадры нужны для ВИЗУАЛА (речь и так в транскрипте), поэтому:
#   - каждая смена сцены → кадр (события: переключения UI/слайдов, склейки);
#   - длинная «дыра» без смен сцены = визуально статично → кадров мало:
#       * тишина  → 1 кадр (пауза/интро/аутро, ничего не происходит);
#       * речь    → редкий добор раз в ~STEP сек (контекст под закадр/говорящую голову).
#   - бюджет MAXF: при переполнении держим события-сцены (по «силе»), режем добор.
#
# Вход (через -v и два файла):
#   DUR, MAXF, MAXGAP, STEP, MINF, MINGAP, SPEECH_RATIO
#   SCENES   — файл "время сила" (по строке на смену сцены)
#   SILENCE  — файл "начало конец" (по строке на интервал тишины)
# Выход: отсортированные по времени таймкоды (по одному в строке), относительно окна.

function speech_ratio(a, b,   silent, i, lo, hi) {
  # доля [a,b], НЕ покрытая тишиной (1 = сплошная речь, 0 = сплошная тишина)
  if (b <= a) return 1
  silent = 0
  for (i = 0; i < msil; i++) {
    lo = (sil_s[i] > a) ? sil_s[i] : a
    hi = (sil_e[i] < b) ? sil_e[i] : b
    if (hi > lo) silent += hi - lo
  }
  return 1 - silent / (b - a)
}

BEGIN {
  # --- читаем карту сцен ---
  ns = 0
  while ((getline line < SCENES) > 0) {
    nf = split(line, a, " ")
    if (nf >= 1 && a[1] != "") { st[ns] = a[1] + 0; ssc[ns] = (nf >= 2 ? a[2] + 0 : 0); ns++ }
  }
  close(SCENES)

  # --- читаем интервалы тишины ---
  msil = 0
  while ((getline line < SILENCE) > 0) {
    nf = split(line, a, " ")
    if (nf >= 2 && a[1] != "") { sil_s[msil] = a[1] + 0; sil_e[msil] = a[2] + 0; msil++ }
  }
  close(SILENCE)

  nc = 0
  # события-сцены как кандидаты (приоритет 2, со «силой»)
  for (i = 0; i < ns; i++) {
    if (st[i] >= 0 && st[i] <= DUR) { ct[nc] = st[i]; cp[nc] = 2; cs[nc] = ssc[i]; nc++ }
  }

  # отсортированная последовательность границ: 0, времена сцен, DUR
  for (i = 0; i < ns; i++) sc[i] = st[i]
  for (i = 0; i < ns; i++) for (j = i + 1; j < ns; j++) if (sc[j] < sc[i]) { tmp = sc[i]; sc[i] = sc[j]; sc[j] = tmp }
  nb = 0; bt[nb++] = 0
  for (i = 0; i < ns; i++) if (sc[i] > 0 && sc[i] < DUR) bt[nb++] = sc[i]
  bt[nb++] = DUR

  # дозабор в «дырах» между сценами (ga/gb — скаляры, чтобы не путать с массивом a из split)
  for (k = 0; k < nb - 1; k++) {
    ga = bt[k]; gb = bt[k + 1]; L = gb - ga
    if (L > MAXGAP) {
      if (speech_ratio(ga, gb) < SPEECH_RATIO) {
        # тишина + статика → 1 кадр в середине
        ct[nc] = (ga + gb) / 2; cp[nc] = 0; cs[nc] = 0; nc++
      } else {
        # речь над статикой → редкий контекстный добор ~раз в STEP
        kk = int(L / STEP); if (kk < 1) kk = 1
        for (j = 1; j <= kk; j++) { ct[nc] = ga + j * L / (kk + 1); cp[nc] = 1; cs[nc] = 0; nc++ }
      }
    }
  }
  # кадр на открытии (часто сцена не начинается ровно с 0)
  ct[nc] = 0.0; cp[nc] = 1; cs[nc] = 0; nc++

  # сортировка кандидатов по времени (с переносом приоритета/силы)
  for (i = 0; i < nc; i++) for (j = i + 1; j < nc; j++) if (ct[j] < ct[i]) {
    tmp = ct[i]; ct[i] = ct[j]; ct[j] = tmp
    tmp = cp[i]; cp[i] = cp[j]; cp[j] = tmp
    tmp = cs[i]; cs[i] = cs[j]; cs[j] = tmp
  }
  # дедуп кадров ближе MINGAP: оставляем лучший (приоритет, затем сила)
  m = 0
  for (i = 0; i < nc; i++) {
    if (m > 0 && ct[i] - ot[m - 1] < MINGAP) {
      if (cp[i] > op[m - 1] || (cp[i] == op[m - 1] && cs[i] > osc[m - 1])) {
        ot[m - 1] = ct[i]; op[m - 1] = cp[i]; osc[m - 1] = cs[i]
      }
    } else { ot[m] = ct[i]; op[m] = cp[i]; osc[m] = cs[i]; m++ }
  }

  # бюджет: при переполнении берём топ-MAXF по (приоритет, сила), потом снова по времени
  if (m > MAXF) {
    for (i = 0; i < m; i++) idx[i] = i
    for (i = 0; i < m; i++) for (j = i + 1; j < m; j++) {
      pi = op[idx[i]]; pj = op[idx[j]]; si = osc[idx[i]]; sj = osc[idx[j]]
      if (pj > pi || (pj == pi && sj > si)) { t = idx[i]; idx[i] = idx[j]; idx[j] = t }
    }
    for (i = 0; i < m; i++) keep[i] = 0
    for (i = 0; i < MAXF; i++) keep[idx[i]] = 1
    m2 = 0
    for (i = 0; i < m; i++) if (keep[i]) { ft[m2++] = ot[i] }
    for (i = 0; i < m2; i++) for (j = i + 1; j < m2; j++) if (ft[j] < ft[i]) { t = ft[i]; ft[i] = ft[j]; ft[j] = t }
    for (i = 0; i < m2; i++) ot[i] = ft[i]
    m = m2
  }

  # пол по минимуму: если кадров совсем мало — равномерно покрываем окно
  if (m < MINF && DUR > 0) {
    m = (MINF + 0)
    for (i = 0; i < m; i++) ot[i] = DUR * (i + 0.5) / m
  }

  for (i = 0; i < m; i++) printf "%.3f\n", ot[i]
}
