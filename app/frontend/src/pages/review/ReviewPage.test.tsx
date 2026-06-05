import { render, screen, cleanup, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, describe, expect, it, vi } from 'vitest';

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

  it('highlights the first locatable OCR fragment when evidence is a summarized phrase', async () => {
    server.use(
      http.get('*/api/tasks/task_001/review', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            status: 'review',
            review_result: {
              ocr_text: '既往史：患者自诉心前区隐痛10+年，一直未予以重视；高血压5+年，最高血压160/92mmHg。现病史：予以“噻托溴铵粉雾剂18ug经口吸入1/日、布地奈德福莫特罗吸入粉雾剂320ug经口吸入2/日”等治疗。',
              pages: [],
              fields: [
                {
                  field_key: 'comorbidities',
                  label: '合并症',
                  value: '心前区隐痛10+年、高血压5+年',
                  status: 'unreviewed',
                  evidence: [
                    {
                      text: '心前区隐痛10+年，一直未予以重视，高血压5+年，最高血压160/92mmHg'
                    }
                  ]
                },
                {
                  field_key: 'maintenance_therapy',
                  label: '长期维持治疗',
                  value: '噻托溴铵粉雾剂18ug经口吸入1/日、布地奈德福莫特罗吸入粉雾剂320ug经口吸入2/日',
                  status: 'unreviewed',
                  evidence: [
                    {
                      text: '予以‘噻托溴铵粉雾剂18ug经口吸入1/日、布地奈德福莫特罗吸入粉雾剂320ug经口吸入2/日’等治疗'
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
    expect(screen.getByText('心前区隐痛10+年', { selector: 'mark' })).toBeTruthy();

    await userEvent.click(screen.getByTestId('review-field-card-maintenance_therapy'));
    expect(screen.getByText('噻托溴铵粉雾剂18ug经口吸入1/日', { selector: 'mark' })).toBeTruthy();
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

  it('does not highlight evidenceText when it exceeds the short-snippet threshold', async () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;

    const longEvidence = '体温：36.7℃ 脉搏：99次/分 呼吸：21次/分 血压：142/87mmHg 身高：175cm 体重：74kg BMI：24.2kg/m² 及多句冗长描述。既往史：患者自诉心前区隐痛10+年，一直未予以重视；高血压5+年，最高血压160/92mmHg。';

    server.use(
      http.get('*/api/tasks/task_001/review', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            status: 'review',
            review_result: {
              ocr_text: `${longEvidence} 后续文本`,
              pages: [],
              fields: [
                {
                  field_key: 'temperature',
                  label: '体温',
                  value: '36.7℃',
                  status: 'unreviewed',
                  evidence: [{ text: longEvidence }],
                },
              ],
            },
          },
        })
      )
    );

    render(<ReviewPage taskId="task_001" />);

    expect(await screen.findByText('来源片段过长（>100 字），不进行高亮，请人工核验')).toBeTruthy();
    expect(document.querySelector('mark')).toBeNull();
    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  it('does not surface evidence_recovered_from_value audit flag as an evidence risk indicator', async () => {
    server.use(
      http.get('*/api/tasks/task_001/review', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            status: 'review',
            review_result: {
              ocr_text: '体温：36.7℃ 脉搏：99次/分',
              pages: [
                {
                  page_id: 'page_001',
                  page_no: 1,
                  preview_url: '/api/tasks/task_001/images/page_001',
                  parsed_text: '体温：36.7℃ 脉搏：99次/分',
                },
              ],
              fields: [
                {
                  field_key: 'temperature',
                  label: '体温',
                  value: '36.7℃',
                  status: 'unreviewed',
                  evidence: [{ page_id: 'page_001', page_no: 1, text: '36.7℃' }],
                  quality_flags: [
                    {
                      flag: 'evidence_recovered_from_value',
                      severity: 'warning',
                      message: '已用 original_value 恢复',
                    },
                  ],
                },
              ],
            },
          },
        })
      )
    );

    render(<ReviewPage taskId="task_001" />);

    expect(await screen.findByLabelText('temperature')).toBeTruthy();
    expect(screen.getByText('36.7℃', { selector: 'mark' })).toBeTruthy();
    expect(screen.queryByText(/证据风险|来源风险/)).toBeNull();
    expect(screen.queryByText(/evidence_recovered_from_value/)).toBeNull();
    expect(screen.queryByLabelText(/已用 original_value 恢复/)).toBeNull();
    expect(screen.queryByLabelText(/重点核验.*evidence_recovered_from_value/)).toBeNull();
  });
});

describe('Reextract entry (FE-MVP-04-05) - new contract: direct overwrite, no warning text', () => {
  beforeEach(() => {
    window.history.pushState({}, '', '/tasks/task_001/review');
  });

  afterEach(() => {
    cleanup();
  });

  it('shows the reextract button only for review/done tasks; not for uploading/processing/failed', async () => {
    // 默认 mock 是 review 状态,按钮应显示
    mockReviewRoutes();
    render(<ReviewPage taskId="task_001" />);
    expect(await screen.findByRole('button', { name: '重新抽取' })).toBeTruthy();

    // done 状态应显示
    cleanup();
    mockReviewRoutesDone();
    render(<ReviewPage taskId="task_001" />);
    expect(await screen.findByRole('button', { name: '重新抽取' })).toBeTruthy();

    // uploading 状态不显示:等待页面进入非可审核的只读态
    cleanup();
    mockReviewRoutesWithStatus('uploading');
    render(<ReviewPage taskId="task_001" />);
    expect(await screen.findByText('任务尚未进入审核')).toBeTruthy();
    expect(screen.queryByRole('button', { name: '重新抽取' })).toBeNull();

    // processing 状态不显示
    cleanup();
    mockReviewRoutesWithStatus('processing');
    render(<ReviewPage taskId="task_001" />);
    expect(await screen.findByText('任务尚未进入审核')).toBeTruthy();
    expect(screen.queryByRole('button', { name: '重新抽取' })).toBeNull();

    // failed 状态不显示
    cleanup();
    mockReviewRoutesWithStatus('failed');
    render(<ReviewPage taskId="task_001" />);
    expect(await screen.findByText('任务处理失败')).toBeTruthy();
    expect(screen.queryByRole('button', { name: '重新抽取' })).toBeNull();
  });

  it('clicking reextract disables the button and calls reextractTaskFromOcr', async () => {
    const user = userEvent.setup();
    const reextractSpy = vi.fn();
    mockReviewRoutes();
    server.use(
      http.post('*/api/tasks/task_001/reextract', () => {
        reextractSpy();
        return HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            status: 'review',
            run_id: 'reextract_20260605T101530Z',
            source: 'ocr_text_only',
            schema_version: 'copd.v1',
            prompt_version: 'copd.prompt.v1',
            candidate_count: 12
          }
        });
      })
    );
    render(<ReviewPage taskId="task_001" />);
    const button = await screen.findByRole('button', { name: '重新抽取' });
    await user.click(button);
    expect(reextractSpy).toHaveBeenCalledTimes(1);
  });

  it('shows in-progress spinner on the reextract button while request is in flight', async () => {
    const user = userEvent.setup();
    let resolveReextract: () => void = () => {};
    mockReviewRoutes();
    server.use(
      http.post('*/api/tasks/task_001/reextract', () =>
        new Promise<Response>((resolve) => {
          resolveReextract = () => resolve(
            HttpResponse.json({
              success: true,
              data: {
                task_id: 'task_001',
                status: 'review',
                run_id: 'reextract_pending_test',
                source: 'ocr_text_only',
                schema_version: 'copd.v1',
                prompt_version: 'copd.prompt.v1',
                candidate_count: 5
              }
            })
          );
        })
      )
    );
    render(<ReviewPage taskId="task_001" />);
    const button = await screen.findByRole('button', { name: '重新抽取' });
    await user.click(button);
    // 点击瞬间:按钮文字变"重新抽取中"且 disabled(不依赖 8s apiRequest 超时)
    const inFlight = await screen.findByRole('button', { name: /重新抽取中/ });
    expect((inFlight as HTMLButtonElement).disabled).toBe(true);
    // 让请求完成,按钮文字恢复
    resolveReextract();
    await waitFor(() => screen.getByRole('button', { name: '重新抽取' }));
  });

  it('cancel button aborts the in-flight reextract and shows a cancelled message', async () => {
    const user = userEvent.setup();
    let resolveReextract: () => void = () => {};
    mockReviewRoutes();
    server.use(
      http.post('*/api/tasks/task_001/reextract', () =>
        new Promise<Response>((resolve) => {
          resolveReextract = () => resolve(
            HttpResponse.json({
              success: true,
              data: {
                task_id: 'task_001',
                status: 'review',
                run_id: 'reextract_will_be_cancelled',
                source: 'ocr_text_only',
                schema_version: 'copd.v1',
                prompt_version: 'copd.prompt.v1',
                candidate_count: 0
              }
            })
          );
        })
      )
    );
    render(<ReviewPage taskId="task_001" />);
    const reextractButton = await screen.findByRole('button', { name: '重新抽取' });
    await user.click(reextractButton);
    // 取消按钮只在 isReextracting 时出现
    const cancelButton = await screen.findByRole('button', { name: '取消' });
    await user.click(cancelButton);
    // catch 路径展示"已取消重新抽取"而非"重新抽取失败"
    expect(await screen.findByText('已取消重新抽取')).toBeTruthy();
    // 按钮文字恢复 + 取消按钮消失
    await waitFor(() => screen.getByRole('button', { name: '重新抽取' }));
    expect(screen.queryByRole('button', { name: '取消' })).toBeNull();
  });

  it('shows run metadata banner after successful reextract and refreshes review data', async () => {
    const user = userEvent.setup();
    mockReviewRoutes();
    server.use(
      http.post('*/api/tasks/task_001/reextract', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            status: 'review',
            run_id: 'reextract_20260605T101530Z',
            source: 'ocr_text_only',
            schema_version: 'copd.v1',
            prompt_version: 'copd.prompt.v1',
            candidate_count: 12
          }
        })
      )
    );
    render(<ReviewPage taskId="task_001" />);
    const button = await screen.findByRole('button', { name: '重新抽取' });
    await user.click(button);

    expect(await screen.findByText(/reextract_20260605T101530Z/)).toBeTruthy();
    expect(screen.getByText(/copd\.v1/)).toBeTruthy();
    expect(screen.getByText(/copd\.prompt\.v1/)).toBeTruthy();
    expect(screen.getByText(/候选\s*12\s*项/)).toBeTruthy();
  });

  it('reopens done task: status pill changes to review after reextract', async () => {
    const user = userEvent.setup();
    mockReviewRoutesDone();
    server.use(
      http.post('*/api/tasks/task_001/reextract', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            status: 'review',
            run_id: 'reextract_done_to_review',
            source: 'ocr_text_only',
            schema_version: 'copd.v1',
            prompt_version: 'copd.prompt.v1',
            candidate_count: 8
          }
        })
      )
    );
    render(<ReviewPage taskId="task_001" />);
    expect(await screen.findByText('已完成')).toBeTruthy();
    await user.click(screen.getByRole('button', { name: '重新抽取' }));
    expect(await screen.findByText('待审核')).toBeTruthy();
  });

  it('shows backend error message on reextract failure without modifying review fields', async () => {
    const user = userEvent.setup();
    mockReviewRoutes();
    server.use(
      http.post('*/api/tasks/task_001/reextract', () =>
        HttpResponse.json(
          { error: { code: 'REEXTRACTION_VALIDATION_FAILED', message: '任务缺少已识别 OCR 文本,无法重新抽取', details: {} } },
          { status: 400 }
        )
      )
    );
    render(<ReviewPage taskId="task_001" />);
    const button = await screen.findByRole('button', { name: '重新抽取' });
    await user.click(button);
    expect(await screen.findByText('任务缺少已识别 OCR 文本,无法重新抽取')).toBeTruthy();
  });

  it('does not render any warning text about not re-OCR / not re-process / not overwriting manual results', async () => {
    mockReviewRoutes();
    render(<ReviewPage taskId="task_001" />);
    await screen.findByRole('button', { name: '重新抽取' });
    const body = document.body.textContent ?? '';
    expect(body).not.toContain('不重新 OCR');
    expect(body).not.toContain('不重新识别');
    expect(body).not.toContain('不重新处理图片');
    expect(body).not.toContain('不覆盖人工');
    expect(body).not.toContain('不覆盖人工已修改');
  });

  it('does not render the reextract banner before reextract is triggered', async () => {
    mockReviewRoutes();
    render(<ReviewPage taskId="task_001" />);
    await screen.findByRole('button', { name: '重新抽取' });
    expect(screen.queryByText(/reextract_/)).toBeNull();
  });

  it('clears the reextract banner when the close button is clicked', async () => {
    const user = userEvent.setup();
    mockReviewRoutes();
    server.use(
      http.post('*/api/tasks/task_001/reextract', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            status: 'review',
            run_id: 'reextract_clear_test',
            source: 'ocr_text_only',
            schema_version: 'copd.v1',
            prompt_version: 'copd.prompt.v1',
            candidate_count: 3
          }
        })
      )
    );
    render(<ReviewPage taskId="task_001" />);
    await user.click(await screen.findByRole('button', { name: '重新抽取' }));
    expect(await screen.findByText(/reextract_clear_test/)).toBeTruthy();
    const closeButton = screen.getByRole('button', { name: '关闭重新抽取摘要' });
    await user.click(closeButton);
    await waitFor(() => expect(screen.queryByText(/reextract_clear_test/)).toBeNull());
  });
});

// 辅助 mock:把 review 任务改成 done
function mockReviewRoutesDone() {
  mockReviewRoutes();
  // 重新覆盖 /api/tasks/task_001 的 status
  server.use(
    http.get('*/api/tasks/task_001', () =>
      HttpResponse.json({
        success: true,
        data: {
          task_id: 'task_001',
          display_name: 'task_001',
          status: 'done',
          created_at: '2026-05-19T10:00:00+08:00',
          updated_at: '2026-05-19T10:05:00+08:00',
          page_count: 2,
          processing_summary: { stage: 'done', status: 'completed', label: '处理完成', progress_percent: 100 },
          review_summary: { confirmed_count: 2, total_count: 2 }
        }
      })
    )
  );
}

function mockReviewRoutesWithStatus(status: 'uploading' | 'processing' | 'failed') {
  server.use(
    http.get('*/api/tasks/task_001', () =>
      HttpResponse.json({
        success: true,
        data: {
          task_id: 'task_001',
          display_name: 'task_001',
          status,
          created_at: '2026-05-19T10:00:00+08:00',
          updated_at: '2026-05-19T10:01:00+08:00',
          page_count: 0,
          error_code: status === 'failed' ? 'TASK_PROCESSING_FAILED' : null,
          error_message: status === 'failed' ? '处理失败' : null
        }
      })
    ),
    http.get('*/api/tasks', () =>
      HttpResponse.json({ success: true, data: { tasks: [] } })
    )
  );
}
