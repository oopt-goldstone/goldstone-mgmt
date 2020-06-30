#include <grpcpp/grpcpp.h>
#include "taish.grpc.pb.h"

#include <memory>
#include <vector>

using grpc::Channel;
using grpc::ClientContext;
using taish::TAI;

class TAIClient {
    public:
        TAIClient(const std::string& host) : m_channel(grpc::CreateChannel(host, grpc::InsecureChannelCredentials())), m_stub(TAI::NewStub(m_channel)) {}
        int ListModule(std::vector<taish::Module>& modules);
        int ListAttributeMetadata(taish::TAIObjectType type, std::vector<taish::AttributeMetadata>& list);
        int GetAttribute(uint64_t oid, uint64_t attr_id, std::string& value);
        int GetAttributeMetadata(taish::TAIObjectType type, const std::string& name, taish::AttributeMetadata& metadata);
        int SetAttribute(uint64_t oid, taish::TAIObjectType type, const std::string& attr, const std::string& value);
    private:
        std::shared_ptr<grpc::Channel> m_channel;
        std::unique_ptr<TAI::Stub> m_stub;
};
