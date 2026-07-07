import deleteIconUrl from './icons/actions/delete.svg?url';
import dragSortIconUrl from './icons/actions/drag-sort.svg?url';
import iconCloseIconUrl from './icons/actions/icon-close.svg?url';
import ocrInfoIconUrl from './icons/actions/ocr-info.svg?url';
import resizeDiagonalIconUrl from './icons/actions/resize-diagonal.svg?url';
import windowResetIconUrl from './icons/actions/window-reset.svg?url';

export const assetUrls = {
  icons: {
    actions: {
      delete: deleteIconUrl,
      dragSort: dragSortIconUrl,
      iconClose: iconCloseIconUrl,
      ocrInfo: ocrInfoIconUrl,
      resizeDiagonal: resizeDiagonalIconUrl,
      windowClose: iconCloseIconUrl,
      windowReset: windowResetIconUrl
    }
  }
} as const;
