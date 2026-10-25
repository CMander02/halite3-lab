import {LoaderCircle,AlertCircle,ArrowUpRight} from 'lucide-react';
import type {ReactNode} from 'react';
export function ErrorBox({message}:{message:string}){return message?<div className="notice error" role="alert"><AlertCircle size={18}/><span>{message}</span></div>:null}
export function Loading(){return <div className="loading" role="status"><LoaderCircle className="spin" size={22}/> 正在加载…</div>}
export function Empty({title,children}:{title:string;children?:ReactNode}){return <div className="empty"><strong>{title}</strong>{children&&<div>{children}</div>}</div>}
export function PageHead({title,description,action,breadcrumb}:{title:string;description?:string;action?:ReactNode;breadcrumb?:ReactNode}){return <><div className="breadcrumb">{breadcrumb||'Halite 3 Arena'}</div><div className="page-head"><div><h1>{title}</h1>{description&&<p>{description}</p>}</div>{action}</div></>}
const labels:Record<string,string>={queued:'等待执行',running:'运行中',complete:'已完成',failed:'失败',cancelled:'已取消',interrupted:'已中断'};
export function Status({value}:{value:string}){return <span className={`status status-${value}`}><i/>{labels[value]||value}</span>}
export function ExternalArrow(){return <ArrowUpRight size={16}/>}
