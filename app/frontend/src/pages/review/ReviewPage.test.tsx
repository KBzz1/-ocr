import { render, screen, cleanup, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { server } from '../../../tests/setupTests';
import { ReviewPage } from './ReviewPage';
import type { ReviewPayload } from '../../api/review';

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
          patient: { patient_id: 'P-A1B2C3D4', name: '测试用例', deleted: false },
          document_type: 'copd_admission_record',
          document_type_label: '入院记录',
          record_date: '2026-06-07',
          record_time: '09:30',
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
  it('renders raw OCR text without stripping tags entities or blank lines', async () => {
    server.use(
      http.get('*/api/tasks/task_001', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            display_name: 'task_001',
            status: 'review',
            created_at: '2026-05-19T10:00:00+08:00',
            page_count: 1,
            processing_summary: { stage: 'done', status: 'completed', label: '处理完成', progress_percent: 100 },
            review_summary: { confirmed_count: 0, total_count: 1 },
          },
        }),
      ),
      http.get('*/api/tasks', () => HttpResponse.json({ success: true, data: { tasks: [] } })),
      http.get('*/api/tasks/task_001/review', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            status: 'review',
            review_result: {
              ocr_text: '<div>## 品后诊断&nbsp;</div>\n\n\n慢阻肺 &amp; 感染  ',
              pages: [
                {
                  page_id: 'page_001',
                  page_no: 1,
                  parsed_text: '<div>## 品后诊断&nbsp;</div>\n\n\n慢阻肺 &amp; 感染  ',
                },
              ],
              fields: [
                {
                  field_key: 'diagnosis_final',
                  label: '最终诊断',
                  value: '慢阻肺',
                  status: 'unreviewed',
                  evidence: [],
                },
              ],
            },
          },
        }),
      ),
    );

    render(<ReviewPage taskId="task_001" />);

    const ocrBox = await screen.findByLabelText('合并 OCR 文本');
    expect(ocrBox.textContent).toBe('<div>## 品后诊断&nbsp;</div>\n\n\n慢阻肺 &amp; 感染  ');
  });

  it('renders_schema_order_even_when_ocr_page_order_is_odd', async () => {
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
            processing_summary: { stage: 'done', status: 'completed', label: '处理完成', progress_percent: 100 },
            review_summary: { confirmed_count: 0, total_count: 3 },
            patient: { patient_id: 'P-A1B2C3D4', name: '测试用例', deleted: false },
            document_type: 'copd_admission_record',
            document_type_label: '入院记录',
            record_date: '2026-06-07',
            record_time: '09:30'
          }
        })
      ),
      http.get('*/api/tasks', () => HttpResponse.json({ success: true, data: { tasks: [] } })),
      http.get('*/api/tasks/task_001/review', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            status: 'review',
            review_result: {
              ocr_text: '## 初步诊断\n慢性阻塞性肺疾病急性加重\n\n## 主诉\n反复咳嗽、咳痰15年，加重伴喘憋3天。\n\n## 现病史\n患者15年前出现反复咳嗽咳痰...',
              pages: [
                {
                  page_id: 'page_001',
                  page_no: 1,
                  preview_url: '/api/tasks/task_001/images/page_001',
                  parsed_text: '## 初步诊断\n慢性阻塞性肺疾病急性加重'
                },
                {
                  page_id: 'page_002',
                  page_no: 2,
                  preview_url: '/api/tasks/task_001/images/page_002',
                  parsed_text: '## 主诉\n反复咳嗽、咳痰15年，加重伴喘憋3天。\n\n## 现病史\n患者15年前出现反复咳嗽咳痰...'
                }
              ],
              fields: [
                {
                  field_key: 'chief_complaint',
                  label: '主诉',
                  value: '反复咳嗽、咳痰15年，加重伴喘憋3天。',
                  status: 'unreviewed',
                  attention_required: false,
                  evidence: [{ page_id: 'page_002', page_no: 2, text: '反复咳嗽、咳痰15年' }]
                },
                {
                  field_key: 'present_illness',
                  label: '现病史',
                  value: '患者15年前出现反复咳嗽咳痰',
                  status: 'unreviewed',
                  attention_required: false,
                  evidence: [{ page_id: 'page_002', page_no: 2, text: '患者15年前出现反复咳嗽咳痰' }]
                },
                {
                  field_key: 'diagnosis_final',
                  label: '最终诊断',
                  value: '慢性阻塞性肺疾病急性加重',
                  status: 'unreviewed',
                  attention_required: false,
                  evidence: [{ page_id: 'page_001', page_no: 1, text: '慢性阻塞性肺疾病急性加重' }]
                }
              ]
            }
          }
        })
      )
    );

    render(<ReviewPage taskId="task_001" />);

    const chiefComplaintCard = await screen.findByTestId('review-field-card-chief_complaint');
    const presentIllnessCard = await screen.findByTestId('review-field-card-present_illness');
    const diagnosisCard = await screen.findByTestId('review-field-card-diagnosis_final');

    // When the backend provides field_groups, the order is schema order:
    // 主诉 before 现病史 before 诊断. OCR/parser page order is odd (diagnosis
    // appears on page 1, but the schema keeps 主诉 first).
    const allCards = Array.from(document.querySelectorAll('[data-testid^="review-field-card-"]'));
    const keysInDom = allCards.map((el) => (el as HTMLElement).getAttribute('data-testid') ?? '');
    const chiefIdx = keysInDom.indexOf('review-field-card-chief_complaint');
    const presentIdx = keysInDom.indexOf('review-field-card-present_illness');
    const diagnosisIdx = keysInDom.indexOf('review-field-card-diagnosis_final');
    expect(chiefIdx).toBeGreaterThanOrEqual(0);
    expect(presentIdx).toBeGreaterThan(chiefIdx);
    expect(diagnosisIdx).toBeGreaterThan(presentIdx);
    expect(chiefComplaintCard).toBeTruthy();
    expect(presentIllnessCard).toBeTruthy();
    expect(diagnosisCard).toBeTruthy();
  });

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

    await userEvent.type(screen.getByLabelText('姓名 字段'), '修正');
    expect(screen.getByText('未保存修改')).toBeTruthy();
  });

  it('shows raw merged OCR text by default in the review workspace', async () => {
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
    const ocrBox = screen.getByLabelText('合并 OCR 文本');
    expect(ocrBox.textContent).toBe('<div style="text-align: center;">第一页文本</div><br><div>第二页文本</div>');
    expect(ocrBox.textContent).toContain('text-align');
    expect(screen.queryByRole('button', { name: '当前页' })).toBeNull();
  });

  it('reviews an individual field from its checkbox and tracks field focus', async () => {
    mockReviewRoutes();
    render(<ReviewPage taskId="task_001" />);

    expect(await screen.findByLabelText('姓名 字段')).toBeTruthy();
    expect(screen.queryByRole('button', { name: '确认' })).toBeNull();
    const reviewCheck = screen.getByRole('button', { name: '审核 姓名' });
    expect(reviewCheck.getAttribute('aria-pressed')).toBe('false');
    expect(reviewCheck.closest('.field-card__value-row')?.querySelector('.field-card__input')).toBe(screen.getByLabelText('姓名 字段'));

    await userEvent.click(reviewCheck);

    expect(screen.getByRole('button', { name: '取消审核 姓名' }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByText('2 个字段，1 个已确认')).toBeTruthy();
    expect(screen.getByText('未保存修改')).toBeTruthy();

    await userEvent.click(screen.getByLabelText('主诉 字段'));
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

  it('highlights a locatable unit from long evidence text', async () => {
    const longEvidence = [
      '现病史：患者反复咳嗽、咳痰15年，活动后气促6年，近期症状加重。',
      '入院后予以吸入治疗并完善相关检查。',
      '体格检查：体温：36.7℃ 脉搏：99次/分 呼吸：21次/分 血压：142/87mmHg。',
      '辅助检查提示血气分析结果需结合临床核对。'
    ].join('');

    server.use(
      http.get('*/api/tasks/task_001/review', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            status: 'review',
            review_result: {
              ocr_text: '体格检查：体温：36.7℃ 脉搏：99次/分 呼吸：21次/分 血压：142/87mmHg。',
              pages: [],
              fields: [
                {
                  field_key: 'vital_signs',
                  label: '生命体征',
                  value: '体温：36.7℃ 脉搏：99次/分',
                  status: 'unreviewed',
                  evidence: [{ text: longEvidence }]
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

    await screen.findByLabelText('姓名 字段');
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
    const field = screen.getByLabelText('姓名 字段') as HTMLInputElement;
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
    expect((screen.getByLabelText('主诉 字段') as HTMLInputElement).value).toBe('头痛三天');
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

    const nameField = await screen.findByLabelText('姓名 字段');
    await userEvent.clear(nameField);
    await userEvent.type(nameField, '李四');
    await userEvent.click(screen.getByRole('button', { name: '一键审核' }));

    // 保存成功 + 完成 都要通过，页面至少有一个"已完成"
    expect((await screen.findAllByText('已完成')).length).toBeGreaterThanOrEqual(1);
  });

  it('shows generic warning markers for suspicious fields without leaking internal quality flags', async () => {
    // 黄色感叹号来自后端 attention_* 或 verification_status=suspicious;
    // 旧版从 quality_flags.flag 字符串派生医生可见文案的逻辑已移除。
    // 这里给后端塞一个"看起来可疑"的 quality_flags 列表,
    // 但字段没有 attention_message,断言 UI 只展示通用重点核验文案,
    // 内部 flag 名/OCR 纠错信息都不出现在医生可见 UI 上。
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

    // 等字段区渲染出来
    await screen.findByLabelText('BMI 字段');

    const flags = screen.getAllByLabelText('重点核验：结果可疑，请核对原文');
    expect(flags).toHaveLength(6);
    for (const flag of flags) {
      expect(flag.textContent).toBe('!');
    }

    // 内部 flag 名 / 旧版 OCR 纠错信息绝不进入医生可见 UI
    const body = document.body.textContent ?? '';
    expect(body).not.toContain('value_not_in_evidence');
    expect(body).not.toContain('negation_or_uncertainty_risk');
    expect(body).not.toContain('possible_duplicate_or_stitching');
    expect(body).not.toContain('ocr_label_ambiguity');
    expect(body).not.toContain('ocr_numeric_conflict');
    expect(body).not.toContain('unit_symbol_ambiguity');
    expect(body).not.toContain('evidence_missing_fallback');
    expect(body).not.toContain('source_section_not_found');
    expect(body).not.toContain('source_hint=');
    // OCR 原文保留:不允许前端把 BHI 静默改写成 BMI
    expect(body).toContain('BHI');
  });

  it('shows a generic warning marker for suspicious fields without attention_required', async () => {
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
                  parsed_text: '体温：36.7℃ 脉搏：99次/分'
                }
              ],
              fields: [
                {
                  field_key: 'temperature',
                  label: '体温',
                  value: '36.7℃',
                  status: 'unreviewed',
                  verification_status: 'suspicious',
                  quality_flags: [
                    { flag: 'value_not_in_evidence', severity: 'warning', message: '字段值中的数字未能在 evidence 中直接找到' }
                  ],
                  evidence: [{ page_id: 'page_001', page_no: 1, text: '36.7℃' }]
                }
              ]
            }
          }
        })
      )
    );

    render(<ReviewPage taskId="task_001" />);

    const flag = await screen.findByLabelText('重点核验：结果可疑，请核对原文');
    expect(flag.textContent).toBe('!');
    expect(flag.closest('[data-testid="review-field-card-temperature"]')).toBeTruthy();
    expect(document.body.textContent ?? '').not.toContain('value_not_in_evidence');
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

  it('highlights a long evidence unit when it is locatable in OCR text', async () => {
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

    expect(await screen.findByText('点击字段可定位原文')).toBeTruthy();
    expect(document.querySelector('mark')?.textContent).toBe(longEvidence);
    expect(scrollIntoView).toHaveBeenCalledWith({ block: 'center', inline: 'nearest' });
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

    expect(await screen.findByLabelText('体温 字段')).toBeTruthy();
    expect(screen.getByText('36.7℃', { selector: 'mark' })).toBeTruthy();
    expect(screen.queryByText(/证据风险|来源风险/)).toBeNull();
    expect(screen.queryByText(/evidence_recovered_from_value/)).toBeNull();
    expect(screen.queryByLabelText(/已用 original_value 恢复/)).toBeNull();
    expect(screen.queryByLabelText(/重点核验.*evidence_recovered_from_value/)).toBeNull();
  });

  it('shows patient name/id, record type, and record date/time in the task card header', async () => {
    mockReviewRoutes();
    render(<ReviewPage taskId="task_001" />);

    const summary = await screen.findByLabelText('任务信息');
    expect(within(summary).getByText('测试用例')).toBeTruthy();
    expect(within(summary).getByText('(P-A1B2C3D4)')).toBeTruthy();
    expect(within(summary).getByText('入院记录')).toBeTruthy();
    // record_date + record_time 拼接
    expect(within(summary).getByText('2026-06-07 09:30')).toBeTruthy();
  });

  it('renders 患者已删除 marker when the patient of a review task is deleted', async () => {
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
            processing_summary: { stage: 'done', status: 'completed', label: '处理完成', progress_percent: 100 },
            review_summary: { confirmed_count: 0, total_count: 1 },
            patient: { patient_id: 'P-E5F6A7B8', name: '已删除患者', deleted: true },
            document_type: 'copd_admission_record',
            document_type_label: '入院记录',
            record_date: '2026-06-07',
            record_time: '09:30'
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
              ocr_text: '',
              pages: [],
              fields: []
            }
          }
        })
      ),
      http.get('*/api/tasks', () => HttpResponse.json({ success: true, data: { tasks: [] } }))
    );
    render(<ReviewPage taskId="task_001" />);

    const summary = await screen.findByLabelText('任务信息');
    expect(within(summary).getByText('患者已删除')).toBeTruthy();
  });

  it('highlights_evidence_by_offset_without_correcting_raw_ocr', async () => {
    server.use(
      http.get('*/api/tasks/task_001/review', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            status: 'review',
            review_result: {
              ocr_text: '## 品后诊断\n慢性阻塞性肺疾病急性加重\n\n## 初步诊断：\n主诉：反复咳嗽、咳痰15年。',
              pages: [
                { page_id: 'page_001', page_no: 1, parsed_text: '## 品后诊断\n慢性阻塞性肺疾病急性加重' },
                { page_id: 'page_002', page_no: 2, parsed_text: '## 初步诊断：\n主诉：反复咳嗽、咳痰15年。' }
              ],
              fields: [
                {
                  field_key: 'diagnosis_final',
                  label: '最终诊断',
                  value: '慢性阻塞性肺疾病急性加重',
                  status: 'unreviewed',
                  evidence: [
                    {
                      id: 'u007',
                      page_id: 'page_001',
                      page_no: 1,
                      text: '慢性阻塞性肺疾病急性加重',
                      start_offset: 7,
                      end_offset: 19
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

    await screen.findByText('点击字段可定位原文');
    const mark = document.querySelector('mark');
    expect(mark).toBeTruthy();
    expect(mark?.textContent).toBe('慢性阻塞性肺疾病急性加重');
    expect(document.body.textContent ?? '').toContain('## 品后诊断');
    expect(document.body.textContent ?? '').not.toContain('## 最后诊断');
  });

  it('falls_back_to_evidence_text_when_offset_is_missing', async () => {
    server.use(
      http.get('*/api/tasks/task_001/review', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            status: 'review',
            review_result: {
              ocr_text: '姓名：张三\n既往史：高血压5年。',
              pages: [],
              fields: [
                {
                  field_key: 'patient_name',
                  label: '姓名',
                  value: '张三',
                  status: 'unreviewed',
                  evidence: [
                    { id: 'u010', page_no: 1, text: '张三' }
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
    const mark = document.querySelector('mark');
    expect(mark?.textContent).toBe('张三');
  });

  it('shows_unlocated_message_without_fabricating_highlight', async () => {
    server.use(
      http.get('*/api/tasks/task_001/review', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            status: 'review',
            review_result: {
              ocr_text: '体温：36.7℃ 脉搏：99次/分',
              pages: [],
              fields: [
                {
                  field_key: 'mystery_field',
                  label: '神秘字段',
                  value: '不在 OCR 里',
                  status: 'unreviewed',
                  evidence: [
                    { id: 'u099', page_no: 1, text: '不存在的来源片段', start_offset: 0, end_offset: 5 }
                  ]
                }
              ]
            }
          }
        })
      )
    );

    render(<ReviewPage taskId="task_001" />);

    expect(await screen.findByText('来源片段未在 OCR 文本中定位，请核对')).toBeTruthy();
    expect(document.querySelector('mark')).toBeNull();
    expect(document.body.textContent ?? '').not.toContain('不存在的来源片段');
  });

  it('uses_saved_page_order_for_ocr_panel', async () => {
    server.use(
      http.get('*/api/tasks/task_001/review', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            status: 'review',
            review_result: {
              ocr_text: '第一页保存内容\n\n第二页保存内容',
              pages: [
                {
                  page_id: 'page_001',
                  page_no: 1,
                  preview_url: '/api/tasks/task_001/images/page_001',
                  parsed_text: '第一页保存内容'
                },
                {
                  page_id: 'page_002',
                  page_no: 2,
                  preview_url: '/api/tasks/task_001/images/page_002',
                  parsed_text: '第二页保存内容'
                }
              ],
              fields: [
                {
                  field_key: 'final_diagnosis',
                  label: '最终诊断',
                  value: '第二页保存内容',
                  status: 'unreviewed',
                  evidence: [
                    {
                      id: 'u201',
                      page_id: 'page_002',
                      page_no: 2,
                      text: '第二页保存内容',
                      start_offset: 9,
                      end_offset: 16
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

    await screen.findByText('点击字段可定位原文');
    const mark = document.querySelector('mark');
    expect(mark?.textContent).toBe('第二页保存内容');
    const tablist = screen.getByRole('tablist', { name: '任务页码' });
    const tabs = within(tablist).getAllByRole('button');
    expect(tabs[0].textContent).toContain('1');
    expect(tabs[1].textContent).toContain('2');
    await userEvent.click(screen.getByTestId('review-field-card-final_diagnosis'));
    expect(screen.getByRole('img', { name: '第 2 页原图' })).toBeTruthy();
  });

  it('renders_raw_ocr_and_schema_fields_for_typo_title_and_odd_page_order', async () => {
    // Task 10: OCR 标题错字(## 品后诊断)+ 页面顺序错乱(诊断页在前,主诉页在后)
    // 审核页必须:
    // 1. OCR 面板展示 ## 品后诊断 原文(不静默改写)
    // 2. 字段区按 schema 顺序: 主诉 在 诊断 之前
    // 3. 点击 诊断 -> 最终诊断,高亮跳到 page 1 实际位置
    // 4. UI 不出现内部 flag 名 / 调试提示
    const mergedText =
      '## 品后诊断\n慢性阻塞性肺疾病急性加重\nⅡ型呼吸衰竭\n\n' +
      '## 初步诊断：\n主诉：反复咳嗽、咳痰20年，喘累2年，加重10余天。';

    const fieldGroups = [
      {
        group_key: 'chief_complaint',
        group_label: '主诉',
        fields: [{ field_key: 'chief_complaint', label: '主诉' }]
      },
      {
        group_key: 'diagnosis',
        group_label: '诊断',
        fields: [
          { field_key: 'diagnosis_preliminary', label: '初步诊断' },
          { field_key: 'diagnosis_final', label: '最终诊断' }
        ]
      },
      {
        group_key: 'past_medical_history',
        group_label: '既往史',
        fields: [{ field_key: 'pmh_nephritis', label: '肾炎' }]
      }
    ];

    server.use(
      http.get('*/api/tasks/task_001', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            display_name: 'task_001',
            status: 'review',
            created_at: '2026-06-18T10:00:00+08:00',
            updated_at: '2026-06-18T10:03:00+08:00',
            page_count: 2,
            processing_summary: {
              stage: 'done',
              status: 'completed',
              label: '处理完成',
              progress_percent: 100
            },
            review_summary: { confirmed_count: 0, total_count: 3 },
            patient: { patient_id: 'P-A1B2C3D4', name: 'OCR错序', deleted: false },
            document_type: 'copd_admission_record',
            document_type_label: '入院记录',
            record_date: '2026-06-18',
            record_time: '09:30'
          }
        })
      ),
      http.get('*/api/tasks', () => HttpResponse.json({ success: true, data: { tasks: [] } })),
      http.get('*/api/tasks/task_001/review', () =>
        HttpResponse.json({
          success: true,
          data: {
            task_id: 'task_001',
            status: 'review',
            review_result: {
              ocr_text: mergedText,
              pages: [
                {
                  page_id: 'page_001',
                  page_no: 1,
                  preview_url: '/api/tasks/task_001/images/page_001',
                  parsed_text: '## 品后诊断\n慢性阻塞性肺疾病急性加重\nⅡ型呼吸衰竭'
                },
                {
                  page_id: 'page_002',
                  page_no: 2,
                  preview_url: '/api/tasks/task_001/images/page_002',
                  parsed_text: '## 初步诊断：\n主诉：反复咳嗽、咳痰20年，喘累2年，加重10余天。'
                }
              ],
              field_groups: fieldGroups,
              fields: [
                {
                  field_key: 'chief_complaint',
                  field_name: '主诉',
                  label: '主诉',
                  value: '主诉：反复咳嗽、咳痰20年，喘累2年，加重10余天。',
                  status: 'unreviewed',
                  attention_required: false,
                  evidence: [
                    {
                      id: 'u_chief',
                      page_id: 'page_002',
                      page_no: 2,
                      text: '主诉：反复咳嗽、咳痰20年，喘累2年，加重10余天。',
                      start_offset: mergedText.indexOf('主诉：反复咳嗽、咳痰20年'),
                      end_offset:
                        mergedText.indexOf('主诉：反复咳嗽、咳痰20年') +
                        '主诉：反复咳嗽、咳痰20年，喘累2年，加重10余天。'.length
                    }
                  ]
                },
                {
                  field_key: 'diagnosis_final',
                  field_name: '最终诊断',
                  label: '最终诊断',
                  value: '慢性阻塞性肺疾病急性加重\nⅡ型呼吸衰竭',
                  status: 'unreviewed',
                  attention_required: false,
                  evidence: [
                    {
                      id: 'u_diag',
                      page_id: 'page_001',
                      page_no: 1,
                      text: '慢性阻塞性肺疾病急性加重\nⅡ型呼吸衰竭',
                      start_offset: mergedText.indexOf('慢性阻塞性肺疾病急性加重'),
                      end_offset:
                        mergedText.indexOf('慢性阻塞性肺疾病急性加重') +
                        '慢性阻塞性肺疾病急性加重\nⅡ型呼吸衰竭'.length
                    }
                  ]
                },
                {
                  field_key: 'pmh_nephritis',
                  field_name: '肾炎',
                  label: '肾炎',
                  value: '',
                  status: 'unreviewed',
                  extraction_status: 'not_found',
                  attention_required: false,
                  evidence: []
                }
              ]
            }
          }
        })
      )
    );

    render(<ReviewPage taskId="task_001" />);

    // 1. OCR 面板展示原文(## 品后诊断 错字保留,不被静默改写)
    expect(await screen.findByText('OCR 合并文本')).toBeTruthy();
    const body = document.body.textContent ?? '';
    expect(body).toContain('## 品后诊断');
    expect(body).not.toContain('## 最后诊断');

    // 2. 字段区按 schema 顺序:主诉 在 诊断 之前
    const allCards = Array.from(document.querySelectorAll('[data-testid^="review-field-card-"]'));
    const keysInDom = allCards.map(
      (el) => (el as HTMLElement).getAttribute('data-testid') ?? ''
    );
    const chiefIdx = keysInDom.indexOf('review-field-card-chief_complaint');
    const diagnosisIdx = keysInDom.indexOf('review-field-card-diagnosis_final');
    expect(chiefIdx).toBeGreaterThanOrEqual(0);
    expect(diagnosisIdx).toBeGreaterThan(chiefIdx);

    // 3. 章节标题(主诉 / 诊断)在 DOM 中按 schema 顺序出现
    const headers = Array.from(document.querySelectorAll('.field-card__header h3')).map(
      (el) => (el as HTMLElement).textContent ?? ''
    );
    const chiefHeader = headers.indexOf('主诉');
    const diagnosisHeader = headers.indexOf('诊断');
    expect(chiefHeader).toBeGreaterThanOrEqual(0);
    expect(diagnosisHeader).toBeGreaterThan(chiefHeader);

    // 4. 点击 最终诊断 字段,OCR 高亮必须跳到 page 1 的"慢性阻塞性肺疾病急性加重"
    await userEvent.click(screen.getByTestId('review-field-card-diagnosis_final'));
    const mark = document.querySelector('mark');
    expect(mark?.textContent).toBe('慢性阻塞性肺疾病急性加重\nⅡ型呼吸衰竭');
    // 当前页应该是第 1 页(诊断页是 page 1)
    expect(screen.getByRole('img', { name: '第 1 页原图' })).toBeTruthy();

    // 5. UI 不出现内部 flag / 调试提示
    expect(body).not.toContain('evidence_missing_fallback');
    expect(body).not.toContain('source_section_not_found');
    expect(body).not.toContain('value_not_in_evidence');
    expect(body).not.toContain('negation_or_uncertainty_risk');
    expect(body).not.toContain('ocr_label_ambiguity');

    // 6. pmh_nephritis 显示"未提及"(not_found 字段不默认黄色感叹号)
    expect(screen.getByText('未提及')).toBeTruthy();
    // 没有"重点核验:" aria-label
    expect(screen.queryByLabelText(/^重点核验[:：]/)).toBeNull();
  });

  it('loads_qwen_batch_fields_and_highlights_anchor_evidence', async () => {
    const payload: ReviewPayload = {
      task_id: 'task_qwen',
      status: 'review' as const,
      review_result: {
        ocr_text: '主诉：反复咳嗽15年。精神睡眠食欲差。',
        pages: [{ page_id: 'p1', page_no: 1, parsed_text: '主诉：反复咳嗽15年。精神睡眠食欲差。' }],
        field_groups: [
          {
            group_key: 'chief_complaint',
            group_label: '主诉',
            fields: [{ field_key: 'chief_complaint', label: '主诉', qwen_type: 'T', qwen_path: ['主诉'] }]
          },
          {
            group_key: 'history_of_present_illness',
            group_label: '现病史',
            fields: [{ field_key: 'hpi_mental_sleep_appetite', label: '精神睡眠食欲', qwen_type: 'J', qwen_path: ['现病史', '精神睡眠食欲'] }]
          }
        ],
        fields: [
          {
            field_key: 'chief_complaint',
            field_name: '主诉',
            label: '主诉',
            value: '反复咳嗽15年',
            final_value: '反复咳嗽15年',
            status: 'unreviewed' as const,
            qwen_type: 'T' as const,
            qwen_path: ['主诉'],
            evidence: [{ id: 's1-s1', text: '主诉：反复咳嗽15年。', start_offset: 0, end_offset: 11 }]
          },
          {
            field_key: 'hpi_mental_sleep_appetite',
            field_name: '精神睡眠食欲',
            label: '精神睡眠食欲',
            value: '异常',
            final_value: '异常',
            status: 'unreviewed' as const,
            qwen_type: 'J' as const,
            qwen_status: 'abnormal' as const,
            qwen_path: ['现病史', '精神睡眠食欲'],
            evidence: [{ id: 's2-s2', text: '精神睡眠食欲差。', start_offset: 11, end_offset: 19 }]
          }
        ]
      }
    };

    render(<ReviewPage taskId="task_qwen" demoPayload={payload} />);

    expect(await screen.findByText('现病史')).toBeTruthy();
    expect(screen.getByRole('button', { name: '异常 精神睡眠食欲' }).getAttribute('aria-pressed')).toBe('true');
    await userEvent.click(screen.getByTestId('review-field-card-hpi_mental_sleep_appetite'));
    expect(screen.getByText('点击字段可定位原文')).toBeTruthy();
    const mark = document.querySelector('mark');
    expect(mark?.textContent).toBe('精神睡眠食欲差。');
  });

  it('uses_evidence_offset_before_text_search_when_evidence_text_repeats', async () => {
    const repeatedText = '精神睡眠食欲差。主诉：反复咳嗽15年。精神睡眠食欲差。';
    const secondOccurrenceStart = repeatedText.lastIndexOf('精神睡眠食欲差。');
    const payload: ReviewPayload = {
      task_id: 'task_qwen_duplicate_evidence',
      status: 'review' as const,
      review_result: {
        ocr_text: repeatedText,
        pages: [{ page_id: 'p1', page_no: 1, parsed_text: repeatedText }],
        field_groups: [
          {
            group_key: 'history_of_present_illness',
            group_label: '现病史',
            fields: [{ field_key: 'hpi_mental_sleep_appetite', label: '精神睡眠食欲', qwen_type: 'J' as const }]
          }
        ],
        fields: [
          {
            field_key: 'hpi_mental_sleep_appetite',
            field_name: '精神睡眠食欲',
            label: '精神睡眠食欲',
            value: '异常',
            final_value: '异常',
            status: 'unreviewed' as const,
            qwen_type: 'J' as const,
            qwen_status: 'abnormal' as const,
            evidence: [{
              id: 's2-s2',
              text: '精神睡眠食欲差。',
              start_offset: secondOccurrenceStart,
              end_offset: secondOccurrenceStart + '精神睡眠食欲差。'.length
            }]
          }
        ]
      }
    };

    render(<ReviewPage taskId="task_qwen_duplicate_evidence" demoPayload={payload} />);

    await screen.findByText('现病史');
    await userEvent.click(screen.getByTestId('review-field-card-hpi_mental_sleep_appetite'));

    const mark = document.querySelector('mark');
    expect(mark?.textContent).toBe('精神睡眠食欲差。');
    expect(mark?.previousSibling?.textContent).toContain('主诉：反复咳嗽15年。');
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
