use std::sync::{Arc, Mutex};
use sysrepo2::change::*;
use sysrepo2::connection::{Connection, SysrepoContextAllocator};
use sysrepo2::session::Session;
use sysrepo2::types::*;
use sysrepo2::Result as SResult;
use sysrepo2::{Error, ErrorCode};

use yang2::context::Context;
use yang2::data::{Data, DataFormat, DataPrinterFlags, DataTree};
use yang2::schema::SchemaNodeKind;

use futures::channel::mpsc::UnboundedReceiver;
use futures::stream::{StreamExt, TryStreamExt};
use rtnetlink::packet::RtnlMessage;
use rtnetlink::proto::NetlinkMessage;
use rtnetlink::proto::NetlinkPayload::InnerMessage;
use rtnetlink::{
    constants::RTMGRP_LINK,
    new_connection, packet,
    packet::rtnl::link::nlas::{Nla, State},
    sys::{AsyncSocket, SocketAddr},
};

use crate::xpath::xpath_split;

fn get_info_from_nlas<'a>(nlas: &'a Vec<Nla>) -> SResult<(&'a str, Option<&'a str>, Option<u32>)> {
    let mut iter = nlas.into_iter();
    let nla = iter.next();

    let ifname = if let Some(Nla::IfName(ref n)) = nla {
        n.as_str()
    } else {
        return Err(Error::new(ErrorCode::Internal));
    };

    let mut state = None;
    let mut mtu = None;

    for nla in iter {
        match nla {
            Nla::OperState(s) => {
                state = match s {
                    State::Up => Some("UP"),
                    State::Dormant => Some("DORMANT"),
                    _ => Some("DOWN"),
                };
            }
            Nla::Mtu(m) => {
                let m = *m; // why needed?
                if m == 65536 {
                    log::info!("{:?}'s MTU({}) is larger than the max value", ifname, m);
                    continue;
                };
                mtu = Some(m);
            }
            _ => (),
        }
    }

    Ok((ifname, state, mtu))
}

fn get_module_top_container(conn: &Arc<Mutex<Connection>>, module_name: &str) -> SResult<String> {
    let a = SysrepoContextAllocator::from_connection(Arc::clone(conn));
    let ctx = Arc::new(Context::from_allocator(Box::new(a))?);
    let schema = ctx
        .get_module_latest(module_name)
        .ok_or(Error::new_with_message(
            ErrorCode::NotFound,
            format!("model name: {} not found", &module_name),
        ))?;
    let mut iter = schema.traverse();
    let top = iter.next().ok_or(Error::new(ErrorCode::Internal))?;
    if top.kind() != SchemaNodeKind::Container {
        return Err(Error::new(ErrorCode::Internal));
    }
    Ok(format!("/{}:{}", module_name, top.name()))
}

struct InnerServer {
    module_name: String,
    module_top_container: String,
    handle: rtnetlink::Handle,
    ctx: Arc<Context>,
}

impl InnerServer {
    fn new(
        conn: &Arc<Mutex<Connection>>,
        module_name: String,
        handle: rtnetlink::Handle,
    ) -> SResult<Self> {
        let sess = Arc::new(Mutex::new(Session::new(conn, DatastoreType::RUNNING)?));
        let a = SysrepoContextAllocator::from_session(Arc::clone(&sess));
        let ctx = Arc::new(Context::from_allocator(Box::new(a))?);

        let module_top_container = get_module_top_container(conn, &module_name)?;

        Ok(InnerServer {
            module_name,
            module_top_container,
            handle,
            ctx,
        })
    }

    fn module_name(&self) -> &str {
        &self.module_name
    }

    fn module_top_container(&self) -> &str {
        &self.module_top_container
    }

    fn get_ifname_from_xpath<'a>(&self, xpath: &'a str) -> Option<&'a str> {
        let elems = xpath_split(xpath).unwrap();
        assert!(elems.len() > 0);
        assert_eq!(elems[0].0, Some(self.module_name()));
        assert_eq!(elems[0].1, "interfaces");
        if elems.len() == 1 {
            return None;
        }
        assert_eq!(elems[1].1, "interface");
        assert_eq!(elems[1].2.len(), 1);

        Some(elems[1].2[0].1)
    }

    async fn module_change_callback(
        &self,
        event_type: EventType,
        _req_id: u32,
        changes: Vec<Change>,
    ) -> SResult<()> {
        if event_type != EventType::CHANGE && event_type != EventType::ENABLED {
            return Ok(());
        }

        for v in changes {
            log::debug!("module_change_callback: {:?}, change {:?}", event_type, v);

            match v.operation {
                ChangeOperation::CREATED | ChangeOperation::MODIFIED => {
                    let new = v.new.as_ref().unwrap();
                    let ifname = self.get_ifname_from_xpath(new.xpath());
                    if ifname.is_none() {
                        continue;
                    }
                    let ifname = ifname.unwrap();
                    let elems = xpath_split(new.xpath()).unwrap();
                    let last = elems.last().unwrap();
                    if last.1 == "admin-status" {
                        let up = new.to_string() == "UP";
                        self.set_admin_status(ifname, up).await?
                    }
                }
                _ => (),
            }
        }
        Ok(())
    }

    async fn set_admin_status(&self, ifname: &str, up: bool) -> SResult<()> {
        log::debug!("ifname: {}, up: {:?}", ifname, up);
        let mut links = self
            .handle
            .link()
            .get()
            .match_name(ifname.to_string())
            .execute();
        let link = links
            .try_next()
            .await
            .map_err(|_| Error::new(ErrorCode::Internal))?;
        let set = self.handle.link().set(link.unwrap().header.index);
        if up { set.up() } else { set.down() }
            .execute()
            .await
            .map_err(|_| Error::new(ErrorCode::Internal))
    }

    async fn oper_get_items_callback(&self, _xpath: &str) -> SResult<DataTree> {
        let mut links = self.handle.link().get().execute();
        let mut data = DataTree::new(&self.ctx);
        while let Some(msg) = links.try_next().await.unwrap() {
            let (ifname, state, mtu) = get_info_from_nlas(&msg.nlas)?;

            let prefix = format!(
                "/{}:{}/interface[name='{}']",
                self.module_name, self.module_top_container, ifname
            );
            let xpath = format!("{}/name", prefix);
            data.new_path(&xpath, Some(ifname), false)?;
            let xpath = format!("{}/state/oper-status", prefix);
            data.new_path(&xpath, state, false)?;
            if let Some(mtu) = mtu {
                let xpath = format!("{}/ethernet/state/mtu", prefix);
                let mtu = mtu.to_string();
                data.new_path(&xpath, Some(mtu.as_str()), false)?;
            }

            let xpath = format!("{prefix}/state/admin-status");
            let admin_status = if msg.header.flags & packet::IFF_UP > 0 {
                "UP"
            } else {
                "DOWN"
            };
            data.new_path(&xpath, Some(&admin_status), false)?;
        }
        Ok(data)
    }
}

pub(crate) struct Server {
    sess: Session,
    inner: Arc<InnerServer>,
}

impl Server {
    pub(crate) fn new(conn: &Arc<Mutex<Connection>>, module_name: &str) -> SResult<Self> {
        let (mut connection, handle, messages) = new_connection().unwrap();
        let mgroup_flags = RTMGRP_LINK;
        let addr = SocketAddr::new(0, mgroup_flags);
        connection
            .socket_mut()
            .socket_mut()
            .bind(&addr)
            .expect("failed to bind");
        tokio::spawn(connection);
        let sess = Session::new(conn, DatastoreType::RUNNING)?;
        let inner = Arc::new(InnerServer::new(conn, module_name.to_string(), handle)?);
        let mut server = Server { sess, inner };

        server.subscribe()?;
        log::info!("Serving {}", module_name);

        let c = Arc::clone(conn);
        let module_name = module_name.to_string();

        tokio::spawn(async move {
            // notification thread
            let ret = Self::notification_loop(c, module_name, messages).await;
            log::error!("notification loop returned: {:?}", ret);
        });

        Ok(server)
    }

    async fn notification_loop(
        conn: Arc<Mutex<Connection>>,
        module_name: String,
        mut messages: UnboundedReceiver<(NetlinkMessage<RtnlMessage>, rtnetlink::sys::SocketAddr)>,
    ) -> SResult<()> {
        let sess = Session::new(&conn, DatastoreType::RUNNING).unwrap();
        let a = SysrepoContextAllocator::from_connection(conn);
        let ctx = Arc::new(Context::from_allocator(Box::new(a)).unwrap());

        let prefix = format!("/{}:interface-link-state-notify-event", &module_name);
        while let Some((message, _)) = messages.next().await {
            if let InnerMessage(packet::rtnl::RtnlMessage::NewLink(m)) = message.payload {
                let (ifname, state, _) = get_info_from_nlas(&m.nlas)?;
                let mut data = DataTree::new(&ctx);

                let xpath = format!("{}/if-name", prefix);
                data.new_path(&xpath, Some(ifname), false)?;
                let xpath = format!("{}/oper-status", prefix);
                data.new_path(&xpath, state, false)?;

                data.print_file(
                    std::io::stdout(),
                    DataFormat::JSON,
                    DataPrinterFlags::WD_ALL | DataPrinterFlags::WITH_SIBLINGS,
                )?;

                sess.notification_send_ly(&mut data, 0, false)?;
            }
        }
        Ok(())
    }

    fn subscribe(&mut self) -> SResult<()> {
        let inner = Arc::clone(&self.inner);
        self.sess.subscribe_module_change_async(
            self.inner.module_name(),
            None,
            Box::new(move |e, r, c| {
                let inner = Arc::clone(&inner);
                Box::pin(async move { inner.module_change_callback(e, r, c).await })
            }),
            0,
            SubscriptionOptions::ENABLED,
        )?;

        let inner = Arc::clone(&self.inner);
        self.sess.subscribe_oper_data_request_async(
            self.inner.module_name(),
            Some(self.inner.module_top_container()),
            Box::new(move |xpath, _| {
                let xpath = xpath.to_string();
                let inner = Arc::clone(&inner);
                Box::pin(async move { inner.oper_get_items_callback(&xpath).await })
            }),
            SubscriptionOptions::DEFAULT,
        )?;

        Ok(())
    }
}
