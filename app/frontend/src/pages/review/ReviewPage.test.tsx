import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { describe, expect, it, vi } from 'vitest';

import { server } from '../../../tests/setupTests';
import { ReviewPage } from './ReviewPage';

function mockReviewRoutes() {
  server.use(
    http.get('*/api/tasks/task_001', () =>
      HttpResponse.json({
        success: true,
        data: {
          task_id: 'task_001',
          display_name: 'task_001',
          status: 'review',
          created_at: '2026-05-19T10:00:00+08:00',
          updated_at: '2026-05-19T10:03:00+08:00',
          page_count: 2,
          processing_summary: {
            stage: 'done',
            status: 'completed',
            label: '处理完成',
            progress_percent: 100
          },
          review_summary: {
            confirmed_count: 0,
            total_count: 2
          },
          status_history: [
            { status: 'uploading', changed_at: '2026-05-19T10:00:00+08:00', message: '创建上传任务' },
            { status: 'processing', changed_at: '2026-05-19T10:01:00+08:00', message: '开始处理' },
            { status: 'review', changed_at: '2026-05-19T10:03:00+08:00', message: '等待人工审核' }
          ]
        }
      })
    ),
    http.get('*/api/tasks', () =>
      HttpResponse.json({
        success: true,
        data: {
          tasks: [
            {
              task_id: 'task_001',
              display_name: 'task_001',
              status: 'review',
              created_at: '2026-05-19T10:00:00+08:00',
              updated_at: '2026-05-19T10:03:00+08:00',
              page_count: 2
            },
            {
              task_id: 'task_002',
              display_name: 'task_002',
              status: 'done',
              created_at: '2026-05-20T10:00:00+08:00',
              updated_at: '2026-05-20T10:03:00+08:00',
              page_count: 1
            }
          ]
        }
      })
    ),
    http.get('*/api/tasks/task_001/review', () =>
      HttpResponse.json({
        success: true,
        data: {
          task_id: 'task_001',
          status: 'review',
          review_result: {
            ocr_text: '第一页文本\n第二页文本',
            pages: [
              {
                page_id: 'page_001',
                page_no: 1,
                preview_url: '/api/tasks/task_001/images/page_001',
                parsed_text: '第一页文本'
              },
              {
                page_id: 'page_002',
                page_no: 2,
                preview_url: '/api/tasks/task_001/images/page_002',
                parsed_text: '第二页文本'
              }
            ],
            fields: [
              {
                field_key: 'patient_name',
                label: '姓名',
                value: '张三',
                status: 'unreviewed',
                evidence: [{ page_id: 'page_001', page_no: 1, text: '张三' }]
              },
              {
                field_key: 'chief_complaint',
                label: '主诉',
                value: '头痛三天',
                status: 'unreviewed',
                evidence: [{ page_id: 'page_002', page_no: 2, text: '头痛三天' }]
              }
            ]
          }
        }
      })
    ),
    http.put('*/api/tasks/task_001/review', async ({ request }) => {
      const body = await request.json() as { fields: Array<Record<string, unknown>> };
      expect(body).toMatchObject({
        fields: expect.arrayContaining([
          expect.objectContaining({ field_key: 'patient_name' })
        ])
      });
      return HttpResponse.json({
        success: true,
        data: {
          task_id: 'task_001',
          status: 'review',
          review_result: {
            ocr_text: '第一页文本\n第二页文本',
            pages: [
              {
                page_id: 'page_001',
                page_no: 1,
                preview_url: '/api/tasks/task_001/images/page_001',
                parsed_text: '第一页文本'
              },
              {
                page_id: 'page_002',
                page_no: 2,
                preview_url: '/api/tasks/task_001/images/page_002',
                parsed_text: '第二页文本'
              }
            ],
            fields: body.fields
          }
        }
      });
    }),
    http.post('*/api/tasks/task_001/complete', () =>
      HttpResponse.json({
        success: true,
        data: {
          task_id: 'task_001',
          status: 'done',
          created_at: '2026-05-19T10:00:00+08:00',
          page_count: 1
        }
      })
    )
  );
}

describe('ReviewPage', () => {
  it('uses the shared workstation navigation shell', async () => {
    mockReviewRoutes();
    render(<ReviewPage taskId="task_001" />);

    expect(await screen.findByRole('navigation', { name: '主要模块' })).toBeTruthy();
    expect(screen.getByRole('link', { name: /首页/ }).getAttribute('href')).toBe('/');
    expect(screen.getByRole('link', { name: /任务管理/ }).getAttribute('href')).toBe('/tasks');
    expect(screen.getByRole('link', { name: /任务详情/ }).getAttribute('aria-current')).toBe('page');
  });

  it('shows one current page image inside the task summary card and switches pages', async () => {
    mockReviewRoutes();
    render(<ReviewPage taskId="task_001" />);

    const summary = await screen.findByLabelText('任务信息');
    expect(summary).toBeTruthy();
    expect(await screen.findByRole('img', { name: '第 1 页原图' })).toBeTruthy();
    expect(screen.queryByRole('img', { name: '第 2 页原图' })).toBeNull();
    expect(screen.queryByLabelText('任务图片')).toBeNull();

    await userEvent.click(screen.getByRole('button', { name: '第 2 页' }));

    expect(screen.getByRole('img', { name: '第 2 页原图' })).toBeTruthy();
    expect(screen.queryByRole('img', { name: '第 1 页原图' })).toBeNull();
  });

  it('shows task and field summary in the review toolbar', async () => {
    mockReviewRoutes();
    render(<ReviewPage taskId="task_001" />);

    await screen.findByText(/待审核/);
    expect(screen.getByLabelText('任务信息')).toBeTruthy();
    expect(screen.getByText('2026/05/19 10:00')).toBeTruthy();
    expect(screen.getByText('处理完成')).toBeTruthy();
    expect(screen.getAllByText('字段').length).toBeGreaterThan(0);
    expect(screen.getByText('待确认')).toBeTruthy();
    expect(screen.getByText('已修改')).toBeTruthy();
    expect(screen.getByLabelText('切换任务')).toBeTruthy();

    await userEvent.type(screen.getByLabelText('patient_name'), '修正');
    expect(screen.getByText('未保存修改')).toBeTruthy();
  });

  it('shows cleaned merged OCR text by default in the review workspace', async () => {
    mockReviewRoutes();
    server.use(
      http.get('*/api/tasks/task_001/review', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            status: 'review',
            review_result: {
              ocr_text: '<div style="text-align: center;">第一页文本</div><br><div>第二页文本</div>',
              pages: [
                {
                  page_id: 'page_001',
                  page_no: 1,
                  preview_url: '/api/tasks/task_001/images/page_001',
                  parsed_text: '<div>第一页文本</div>'
                },
                {
                  page_id: 'page_002',
                  page_no: 2,
                  preview_url: '/api/tasks/task_001/images/page_002',
                  parsed_text: '<div>第二页文本</div>'
                }
              ],
              fields: [
                {
                  field_key: 'patient_name',
                  label: '姓名',
                  value: '张三',
                  status: 'unreviewed',
                  evidence: [{ page_id: 'page_001', page_no: 1, text: '张三' }]
                }
              ]
            }
          }
        })
      )
    );
    render(<ReviewPage taskId="task_001" />);

    await screen.findByText('字段校对');
    expect(screen.getByText(/第一页文本/)).toBeTruthy();
    expect(screen.getByText(/第二页文本/)).toBeTruthy();
    expect(screen.queryByText(/text-align/)).toBeNull();
    expect(screen.queryByRole('button', { name: '当前页' })).toBeNull();
  });

  it('reviews an individual field from its checkbox and tracks field focus', async () => {
    mockReviewRoutes();
    render(<ReviewPage taskId="task_001" />);

    expect(await screen.findByLabelText('patient_name')).toBeTruthy();
    expect(screen.queryByRole('button', { name: '确认' })).toBeNull();
    const reviewCheck = screen.getByRole('button', { name: '审核 姓名' });
    expect(reviewCheck.getAttribute('aria-pressed')).toBe('false');
    expect(reviewCheck.closest('.field-card__value-row')?.querySelector('.field-card__input')).toBe(screen.getByLabelText('patient_name'));

    await userEvent.click(reviewCheck);

    expect(screen.getByRole('button', { name: '取消审核 姓名' }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByText('2 个字段，1 个已确认')).toBeTruthy();
    expect(screen.getByText('未保存修改')).toBeTruthy();

    await userEvent.click(screen.getByLabelText('chief_complaint'));
    expect(screen.getByRole('img', { name: '第 2 页原图' })).toBeTruthy();
  });

  it('highlights selected field evidence in OCR and reports missing source text', async () => {
    server.use(
      http.get('*/api/tasks/task_001/review', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            status: 'review',
            review_result: {
              ocr_text: '姓名：张三\n第二页没有来源',
              pages: [
                {
                  page_id: 'page_001',
                  page_no: 1,
                  preview_url: '/api/tasks/task_001/images/page_001',
                  parsed_text: '姓名：张三'
                },
                {
                  page_id: 'page_002',
                  page_no: 2,
                  preview_url: '/api/tasks/task_001/images/page_002',
                  parsed_text: '第二页没有来源'
                }
              ],
              fields: [
                {
                  field_key: 'patient_name',
                  label: '姓名',
                  value: '张三',
                  status: 'unreviewed',
                  evidence: [{ page_id: 'page_001', page_no: 1, text: '张三' }]
                },
                {
                  field_key: 'chief_complaint',
                  label: '主诉',
                  value: '头痛三天',
                  status: 'unreviewed',
                  evidence: [{ page_id: 'page_002', page_no: 2, text: '头痛三天' }]
                }
              ]
            }
          }
        })
      )
    );

    render(<ReviewPage taskId="task_001" />);

    expect(await screen.findByText('点击字段可定位原文')).toBeTruthy();
    expect(screen.getByText('张三', { selector: 'mark' })).toBeTruthy();

    await userEvent.click(screen.getByTestId('review-field-card-chief_complaint'));
    expect(screen.getByText('来源文本未在当前 OCR 中定位')).toBeTruthy();
  });

  it('highlights OCR evidence after stripping markup from long source text', async () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;

    server.use(
      http.get('*/api/tasks/task_001/review', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            status: 'review',
            review_result: {
              ocr_text: '体温：36.7℃ 脉搏：99次/分\n\n发育正常，营养良好。',
              pages: [],
              fields: [
                {
                  field_key: 'temperature',
                  label: '体温',
                  value: '36.7℃',
                  status: 'unreviewed',
                  evidence: [
                    {
                      text: '体温：36.7℃ 脉搏：99次/分<br><div style="text-align: center;"><img src="imgs/physical.jpg" /></div>发育正常，营养良好。'
                    }
                  ]
                }
              ]
            }
          }
        })
      )
    );

    render(<ReviewPage taskId="task_001" />);

    expect(await screen.findByText('点击字段可定位原文')).toBeTruthy();
    expect(document.querySelector('mark')?.textContent).toContain('体温：36.7℃ 脉搏：99次/分');
    expect(scrollIntoView).toHaveBeenCalledWith({ block: 'center', inline: 'nearest' });
  });

  it('does not complete from shortcut while a save request is in flight', async () => {
    mockReviewRoutes();
    const completeSpy = vi.fn();
    const saveGate: { finish?: () => void } = {};

    server.use(
      http.put('*/api/tasks/task_001/review', async ({ request }) => {
        const body = await request.json() as { fields: Array<Record<string, unknown>> };
        await new Promise<void>((resolve) => {
          saveGate.finish = resolve;
        });
        return HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            status: 'review',
            review_result: {
              ocr_text: '第一页文本\n第二页文本',
              pages: [
                { page_id: 'page_001', page_no: 1, preview_url: '/api/tasks/task_001/images/page_001', parsed_text: '第一页文本' },
                { page_id: 'page_002', page_no: 2, preview_url: '/api/tasks/task_001/images/page_002', parsed_text: '第二页文本' }
              ],
              fields: body.fields
            }
          }
        });
      }),
      http.post('*/api/tasks/task_001/complete', () => {
        completeSpy();
        return HttpResponse.json({
          success: true,
          data: { task_id: 'task_001', status: 'done', created_at: '2026-05-19T10:00:00+08:00', page_count: 1 }
        });
      })
    );

    render(<ReviewPage taskId="task_001" />);

    await screen.findByLabelText('patient_name');
    await userEvent.click(screen.getByRole('button', { name: '保存修改' }));
    await userEvent.keyboard('{Control>}{Enter}{/Control}');

    expect(completeSpy).not.toHaveBeenCalled();
    saveGate.finish?.();
    expect(await screen.findByText('已保存')).toBeTruthy();
    expect(completeSpy).not.toHaveBeenCalled();
  });

  it('shows images, OCR text, editable fields, complete and export actions', async () => {
    mockReviewRoutes();
    render(<ReviewPage taskId="task_001" />);

    expect(await screen.findByText('OCR 合并文本')).toBeTruthy();
    const field = screen.getByLabelText('patient_name') as HTMLInputElement;
    expect(field.value).toBe('张三');

    await userEvent.clear(field);
    await userEvent.type(field, '李四');
    await userEvent.click(screen.getByRole('button', { name: '保存修改' }));

    expect((await screen.findAllByText('已保存')).length).toBeGreaterThanOrEqual(1);
    await userEvent.click(screen.getByRole('button', { name: '一键审核' }));
    expect((await screen.findAllByText('已完成')).length).toBeGreaterThanOrEqual(1);
    expect((screen.getByRole('button', { name: '导出 JSON' }) as HTMLButtonElement).disabled).toBe(false);
    expect((screen.getByRole('button', { name: '导出 Excel' }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('shows backend field labels and extracted candidate values', async () => {
    server.use(
      http.get('*/api/tasks/task_001/review', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            status: 'review',
            review_result: {
              ocr_text: '主诉：头痛三天',
              pages: [],
              fields: [
                {
                  field_key: 'chief_complaint',
                  field_name: '主诉',
                  auto_value: '头痛三天',
                  final_value: '',
                  status: 'unreviewed'
                }
              ]
            }
          }
        })
      )
    );

    render(<ReviewPage taskId="task_001" />);

    expect(await screen.findByText('主诉')).toBeTruthy();
    expect((screen.getByLabelText('chief_complaint') as HTMLInputElement).value).toBe('头痛三天');
  });

  it('saves every field as confirmed before completing from one-click review', async () => {
    mockReviewRoutes();
    server.use(
      http.put('*/api/tasks/task_001/review', async ({ request }) => {
        const body = (await request.json()) as { fields: Array<Record<string, unknown>> };
        expect(body).toMatchObject({
          fields: expect.arrayContaining([
            expect.objectContaining({ field_key: 'patient_name', value: '李四', status: 'confirmed' }),
            expect.objectContaining({ field_key: 'chief_complaint', value: '头痛三天', status: 'confirmed' })
          ])
        });
        return HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            status: 'review',
            review_result: {
              ocr_text: '第一页文本\n第二页文本',
              pages: [
                {
                  page_id: 'page_001',
                  page_no: 1,
                  preview_url: '/api/tasks/task_001/images/page_001',
                  parsed_text: '第一页文本'
                },
                {
                  page_id: 'page_002',
                  page_no: 2,
                  preview_url: '/api/tasks/task_001/images/page_002',
                  parsed_text: '第二页文本'
                }
              ],
              fields: [
                { field_key: 'patient_name', label: '姓名', value: '李四', status: 'modified' },
                { field_key: 'chief_complaint', label: '主诉', value: '头痛三天', status: 'confirmed' }
              ]
            }
          }
        });
      })
    );
    render(<ReviewPage taskId="task_001" />);

    const nameField = await screen.findByLabelText('patient_name');
    await userEvent.clear(nameField);
    await userEvent.type(nameField, '李四');
    await userEvent.click(screen.getByRole('button', { name: '一键审核' }));

    // 保存成功 + 完成 都要通过，页面至少有一个"已完成"
    expect((await screen.findAllByText('已完成')).length).toBeGreaterThanOrEqual(1);
  });

  it('shows instant evidence-missing and OCR ambiguity risk indicators', async () => {
    server.use(
      http.get('*/api/tasks/task_001/review', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            status: 'review',
            review_result: {
              ocr_text: 'BHI:24.2kg/m2\n否认发热\n重复重复',
              pages: [{ page_id: 'page_001', page_no: 1, preview_url: '/api/tasks/task_001/images/page_001', parsed_text: 'BHI:24.2kg/m2\n否认发热\n重复重复' }],
              fields: [
                {
                  field_key: 'bmi',
                  label: 'BMI',
                  value: '24.2kg/m2',
                  status: 'unreviewed',
                  extraction_status: 'extracted',
                  verification_status: 'suspicious',
                  quality_flags: [{ flag: 'value_not_in_evidence', severity: 'warning', message: '字段值中的数字未能在 evidence 中直接找到' }],
                  ocr_correction: { applied: true, raw: 'BHI', normalized: 'BMI', reason: '单位 kg/m2' }
                },
                {
                  field_key: 'fever',
                  label: '发热',
                  value: '无',
                  status: 'unreviewed',
                  verification_status: 'suspicious',
                  quality_flags: [{ flag: 'negation_or_uncertainty_risk', severity: 'warning', message: 'evidence 附近存在否定或不确定语气' }]
                },
                {
                  field_key: 'duplicate',
                  label: '重复片段',
                  value: '重复',
                  status: 'unreviewed',
                  verification_status: 'suspicious',
                  quality_flags: [{ flag: 'possible_duplicate_or_stitching', severity: 'warning', message: '文本中存在高相似重复片段' }]
                },
                {
                  field_key: 'blood_gas_pao2',
                  label: '血气 PaO2/PO2',
                  value: '76.00mmHg',
                  status: 'unreviewed',
                  verification_status: 'suspicious',
                  quality_flags: [{ flag: 'ocr_label_ambiguity', severity: 'warning', message: 'OCR 中检验项目名疑似错读，请核对原文' }]
                },
                {
                  field_key: 'pulse',
                  label: '脉搏',
                  value: '9次/分',
                  status: 'unreviewed',
                  verification_status: 'suspicious',
                  quality_flags: [{ flag: 'ocr_numeric_conflict', severity: 'warning', message: '同一字段附近存在不一致数值，请核对原文' }]
                },
                {
                  field_key: 'wbc',
                  label: '白细胞',
                  value: '6.63+10^9/L',
                  status: 'unreviewed',
                  verification_status: 'suspicious',
                  quality_flags: [{ flag: 'unit_symbol_ambiguity', severity: 'warning', message: '检验单位符号需核对' }]
                }
              ]
            }
          }
        })
      )
    );

    render(<ReviewPage taskId="task_001" />);

    const riskFlag = await screen.findByLabelText('重点核验：未找到证据；最开始提取片段：24.2kg/m2');
    expect(riskFlag).toBeTruthy();
    expect(riskFlag.getAttribute('data-tooltip')).toBe('未找到证据；最开始提取片段：24.2kg/m2');
    expect(riskFlag.getAttribute('title')).toBeNull();
    expect(await screen.findByLabelText('重点核验：OCR 中检验项目名疑似错读，请核对原文')).toBeTruthy();
    expect(await screen.findByLabelText('重点核验：同一字段附近存在不一致数值，请核对原文')).toBeTruthy();
    expect(await screen.findByLabelText('重点核验：检验单位符号需核对')).toBeTruthy();
    expect(screen.queryByText('需核验')).toBeNull();
    expect(screen.queryByText('需重点核验')).toBeNull();
    expect(screen.queryByText('字段值中的数字未能在 evidence 中直接找到')).toBeNull();
    expect(screen.queryByText(/OCR.*BHI.*BMI/)).toBeNull();
    expect(screen.queryByLabelText(/否定或不确定语气/)).toBeNull();
    expect(screen.queryByLabelText(/高相似重复片段/)).toBeNull();
  });

  it('shows a message when task completion validation fails', async () => {
    mockReviewRoutes();
    server.use(
      http.post('*/api/tasks/task_001/complete', () =>
        HttpResponse.json(
          {
            error: {
              code: 'REVIEW_NOT_COMPLETED',
              message: '仍有字段未审核',
              details: {}
            }
          },
          { status: 400 }
        )
      )
    );

    render(<ReviewPage taskId="task_001" />);

    await screen.findByText('OCR 合并文本');
    await userEvent.click(screen.getByRole('button', { name: '一键审核' }));

    expect(await screen.findByText('仍有字段未审核')).toBeTruthy();
  });

  it('opens a failed task as task detail with failure reason and retry action instead of editable review', async () => {
    server.use(
      http.get('*/api/tasks/task_failed', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_failed',
            display_name: 'task_failed',
            status: 'failed',
            created_at: '2026-05-19T10:00:00+08:00',
            updated_at: '2026-05-19T10:02:00+08:00',
            page_count: 2,
            error_code: 'ALGORITHM_MODULE_NOT_CONFIGURED',
            error_message: 'OCR/结构化模块未配置，请检查本地配置',
            status_history: [
              { to_status: 'uploading', changed_at: '2026-05-19T10:00:00+08:00', reason: '创建上传任务' },
              { to_status: 'failed', changed_at: '2026-05-19T10:02:00+08:00', reason: '算法模块未配置' }
            ]
          }
        })
      ),
      http.post('*/api/tasks/task_failed/process', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_failed',
            status: 'processing',
            created_at: '2026-05-19T10:00:00+08:00',
            page_count: 2,
            processing_summary: {
              stage: 'queued',
              status: 'running',
              label: '等待处理',
              progress_percent: 5
            }
          }
        })
      )
    );

    render(<ReviewPage taskId="task_failed" />);

    expect(await screen.findByLabelText('任务信息')).toBeTruthy();
    expect(screen.getByText('OCR/结构化模块未配置，请检查本地配置')).toBeTruthy();
    expect(screen.queryByLabelText('结构化字段')).toBeNull();

    await userEvent.click(screen.getByRole('button', { name: '重新处理' }));
    expect(await screen.findByText('已提交重新处理')).toBeTruthy();
    expect(screen.getByText('处理中')).toBeTruthy();
  });

  it('opens a processing task as read-only task detail with progress', async () => {
    server.use(
      http.get('*/api/tasks/task_processing', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_processing',
            display_name: 'task_processing',
            status: 'processing',
            created_at: '2026-05-19T10:00:00+08:00',
            page_count: 3,
            processing_summary: {
              stage: 'document_parsing',
              status: 'running',
              label: 'OCR 文档解析',
              progress_percent: 55
            }
          }
        })
      )
    );

    render(<ReviewPage taskId="task_processing" />);

    expect(await screen.findByText('OCR 文档解析')).toBeTruthy();
    expect(screen.getByRole('progressbar', { name: '任务处理进度' }).getAttribute('aria-valuenow')).toBe('55');
    expect(screen.queryByLabelText('结构化字段')).toBeNull();
    expect(screen.queryByRole('button', { name: '一键审核' })).toBeNull();
  });
});
