import {api} from '../api/client.js';
import {empty,errorSlot} from '../components/common/layout.js';
import {report} from '../components/common/report.js';
import {table} from '../components/common/table.js';
import {decisions,states} from '../constants/enums.js';
import {bindForm} from '../hooks/forms.js';
import {state} from '../stores/session.js';
import {fieldInput} from '../types/fields.js';
import {esc,formData,time} from '../utils/html.js';

function factoryRows(manufacturers) {
  return Object.values(manufacturers).map(entry => ({
    厂牌: entry.manufacturer,
    状态: entry.released ? '放行' : '不放行',
    门槛: entry.released ? `相似度≥${entry.min_score} · 分差≥${entry.min_margin}` : '—',
    留批认对: entry.released ? `${entry.known_correct}/${entry.known_usable}` : '—',
    模拟误挂: entry.released ? `${entry.new_attached}/${entry.new_usable}` : '—',
    依据: entry.released ? `误挂率 ${(entry.false_attach_rate * 100).toFixed(1)}%` : `${entry.reason}（已知样本 ${entry.known_usable}，模拟样本 ${entry.new_usable}）`,
  }));
}

export async function analysis() {
  const profile = state.profile;
  const [datasets,runs,versions] = await Promise.all([api('/datasets'),api('/runs'),api('/thresholds')]);
  const form = state.account.role === 'analyst' && datasets.length ? `<form id="queue" class="inline-form"><label>数据版本<select name="dataset_id">${datasets.map(row => `<option value="${row.id}" ${row.id === state.datasetId ? 'selected' : ''}>${esc(row.name)} · #${row.id}</option>`).join('')}</select></label>${profile.options.map(field => `<label>${esc(field.label)}${fieldInput(field,esc)}</label>`).join('')}<button type="submit">提交计算</button>${errorSlot}</form>` : empty(datasets.length ? '分析员可提交计算。' : '先导入数据版本。', '#1', '查看数据台账');
  const active = versions.find(row => row.active);
  const detail = active ? await api(`/thresholds/${active.id}`) : null;
  const hashFields = profile.options.filter(field => field.key === 'hash_dimension' || field.key === 'ngram_range');
  const calibrator = state.account.role === 'analyst' && datasets.length ? `<form id="calibrate" class="inline-form"><label>数据版本<select name="dataset_id">${datasets.map(row => `<option value="${row.id}" ${row.id === state.datasetId ? 'selected' : ''}>${esc(row.name)} · #${row.id}</option>`).join('')}</select></label>${hashFields.map(field => `<label>${esc(field.label)}${fieldInput(field,esc)}</label>`).join('')}<button type="submit">校准并切换门槛</button>${errorSlot}</form>` : '<p class="hint">分析员可用已签认铭牌校准按厂门槛。</p>';
  const current = detail ? `<p class="hint">启用中：版本 #${detail.id} · 数据版本 #${detail.dataset_id} · ${detail.hash_dimension} 桶 · 片段 ${esc(detail.ngram_range)} · ${esc(detail.owner)} · ${time(detail.created)}</p>${table(factoryRows(detail.content.manufacturers))}` : '<p class="hint">尚未校准，分析按手动相似度和分差门槛运行。</p>';
  const history = table(versions.map(row => ({版本:row.id,数据版本:row.dataset_id,哈希:`${row.hash_dimension} 桶 · ${esc(row.ngram_range)}`,状态:row.active ? '启用中' : '已替换',校准人:row.owner,时间:time(row.created)})));
  const runRows = runs.map(run => ({任务:{link:`#3/${run.id}`,text:`#${run.id}`},数据版本:run.dataset_id,门槛:run.thresholds ? `校准 #${run.thresholds.version}` : '手动参数',状态:states[run.state],提交时间:time(run.created),复核:decisions[run.decision] ?? '待复核'}));
  return `<section><h2>计算条件</h2><p>${esc(profile.method)}</p>${form}</section><section><h2>按厂门槛校准</h2><p>用数据版本中的已签认铭牌逐厂留出一个来源批次评估：候选池排除同厂同文记录，模拟新件号时再排除其全部别名；误挂率不超 5% 时选取认对已知件最多的相似度与分差门槛。样本缺一类的厂不放行建议。全部厂算完后一次性切换，排队中的分析各自锁定一版门槛和依据。</p>${calibrator}${current}${history}</section><section><h2>分析记录</h2>${table(runRows)}</section>`;
}

export async function currentRun() {
  const runs = await api('/runs');
  const chosen = runs.find(item => item.id === state.runId) || runs[0];
  return {runs,run:chosen ? await api(`/runs/${chosen.id}`) : null};
}

export function chooseRun(runs, selected) {
  return `<label>分析任务<select id="pick-run">${runs.map(row => `<option value="${row.id}" ${selected === row.id ? 'selected' : ''}>#${row.id} · ${states[row.state]} · ${time(row.created)}</option>`).join('')}</select></label>`;
}

export async function results() {
  const {runs,run} = await currentRun();
  if (!run) return empty('提交一条分析任务后可在这里查看结果。','#2','配置分析');
  const result = run.result ? report(run.result) : `<p ${run.error ? 'class="error"' : 'data-poll'}>${esc(run.error || states[run.state])}</p>`;
  return `<section>${chooseRun(runs,run.id)}<p class="hint">数据版本 #${run.dataset_id} · 计算状态 ${states[run.state]}</p>${result}${run.result ? `<a class="button" href="#4/${run.id}">进入业务复核</a>` : '<a href="#2">回到分析条件</a>'}</section>`;
}

export function bindAnalysis(root, section, refresh) {
  bindForm(root, '#queue', async form => {
    const {dataset_id,...options} = formData(form);
    const run = await api('/runs',{dataset_id:Number(dataset_id),options});
    location.hash = `3/${run.id}`;
  });
  bindForm(root, '#calibrate', async form => {
    const {dataset_id,...options} = formData(form);
    const result = await api(`/datasets/${dataset_id}/calibrate`,{options});
    const released = Object.values(result.manufacturers).filter(entry => entry.released).length;
    state.status = `门槛版本 #${result.id} 已启用：${released} 个厂牌放行，其余转人工复核。`;
  }, refresh);
  root.querySelector('#pick-run')?.addEventListener('change', event => {location.hash = `${section}/${event.target.value}`;});
}
