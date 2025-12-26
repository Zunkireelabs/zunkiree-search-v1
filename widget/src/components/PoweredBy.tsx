import React from 'react';
import { PoweredByProps } from '../types';

export const PoweredBy: React.FC<PoweredByProps> = ({ show }) => {
  if (!show) {
    return null;
  }

  return (
    <div className="zk-powered-by" id="zk-powered-by">
      <span className="zk-powered-by__icon">✨</span>
      <span>Powered by</span>
      <a
        href="https://zunkiree.ai"
        target="_blank"
        rel="noopener noreferrer"
        className="zk-powered-by__link"
      >
        Zunkiree AI
      </a>
    </div>
  );
};

export default PoweredBy;
